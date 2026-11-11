"""Extend the retained group-six request reader with explicit T7 replay.

The original ordinary reader is retained at
sft-group6-actor-request-review-v1/reconstruct.py (4f5665135e4276f6...).
Only the public-memory transitions are added; no model, browser or claim runs.
"""
from copy import deepcopy
import hashlib
import json


def require(ok, message):
    if not ok: raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def reconstruct(*, trace, steps, generations, skill, goal, task_id, snapshot_id,
                model_path, protocol, count_tokens, fit_messages, observed_targets,
                validate_upload_action, skill_fingerprint, initial_guard, initial_observation,
                actor_memory_policy=None):
    """Replay the frozen ordinary request pipeline against raw step observations.

    Policy selection, message formatting, line budgeting, parsing and observed
    targets are original capsule callables. Only the small recorded-history loop
    is explicit here, including parse-failure observation/error transitions.
    """
    require(trace.get('error') is None and trace['sample_status'] == 'completed', 'Completed ordinary trace required')
    require(trace['task_id'] == task_id and trace['domain'] == 'gitlab' and trace['task_instruction'] == goal
            and trace['model'] == model_path, 'Actual source/goal/model differs')
    require(trace['rounds'] == len(generations) and generations and trace['rounds'] <= 20,
            'Every real generation must have a saved request')
    require([r['step'] for r in steps] == list(range(len(steps))) and steps[0]['action'] is None,
            'Consecutive actual browser steps required')
    expected_seed = (42 + int(hashlib.sha256(task_id.encode()).hexdigest()[:8], 16)) % (2**31)
    provenance = trace['provenance']
    require(trace['seed'] == expected_seed and trace['rollout_index'] == 0
            and provenance['actor_protocol'] == protocol.name == 'structured_observed'
            and provenance['generated_skill_sha256'] == skill_fingerprint(skill)
            and provenance['website_snapshot_id'] == snapshot_id
            and provenance['stopping_policy']['max_steps'] == 20,
            'Actual skill/snapshot/seed/protocol/step budget differs')
    require(protocol.answer_fields is None, 'This group-navigation source has no public query answer schema')
    from .actor_event_memory import memory_for_policy
    memory = memory_for_policy(actor_memory_policy)
    if memory is None:
        require('actor_memory_evidence' not in trace['task_output'], 'Undeclared Actor memory evidence')
    else:
        from types import SimpleNamespace
        memory.start(f'browser:{task_id}:rollout:0')
        memory.validate_backend_budget(SimpleNamespace(settings=SimpleNamespace(max_input_tokens=16384)))
        require('actor_memory_evidence' in trace['task_output'], 'Declared Actor memory evidence missing')
    messages = trace['messages']
    require(len(messages) == 2 * len(generations) + 1
            and [r['turn'] for r in messages] == list(range(len(messages))), 'Complete recorded message sequence required')
    skills = [json.dumps(skill, ensure_ascii=False)]
    history = []; step_index = 0; observation = deepcopy(steps[0]['observation']); rows = []; reasons = []
    require(provenance['start_url'] == observation['url'], 'Initial source URL differs')
    for index, generation in enumerate(generations):
        before, response = messages[2 * index:2 * index + 2]
        require(before['role'] == 'user' and response['role'] == 'assistant', 'Request/response ordering differs')
        require(generation['status'] == 'complete' and generation['seed'] == expected_seed + index
                and generation['max_new_tokens'] == 512, 'Actual bounded completed generation differs')
        if memory is None:
            selected = protocol.prepare_observation(goal, observation, history, token_counter=count_tokens,
                                                   action_description=None, skills=skills)
            requested = protocol.messages(goal, selected, history, action_description=None, skills=skills)
        else:
            selected, requested = memory.prepare(protocol, goal, observation, history, token_counter=count_tokens,
                                                 action_description=None, skills=skills)
        actual, budget = fit_messages(requested, count_tokens, 16384)
        require(actual == generation['messages'], 'Actual dispatched messages do not reconstruct at generation ' + str(index))
        require(budget == generation['observation_budget'] and budget['input_tokens'] == generation['input_tokens']
                and 0 < generation['input_tokens'] <= 16384, 'Actual observation budget/token count differs')
        if memory is not None:
            memory.acknowledge(index, actual)
        reply = generation['response']
        require(reply['text'] == response['content'] and reply['prompt_tokens'] == count_tokens(actual),
                'Actual response or backend prompt token count differs')
        require(type(reply['completion_tokens']) is int and 0 <= reply['completion_tokens'] <= 512,
                'Actual completion token budget differs')
        if index == 0:
            # InitialObservationGuard runs beneath MeasuredActor. Recompute its
            # second no-op fit and exact observed-initial binding too.
            guarded, guard_budget = fit_messages(actual, count_tokens, 16384)
            require(guarded == actual, 'Initial guard changed actual dispatched request')
            body = json.loads(guarded[-1]['content'])
            sha = lambda value: hashlib.sha256(value.encode()).hexdigest()
            require(initial_guard == dict(version='stage1-initial-request-binding-v1', equal=True,
                expected_sha256=sha(initial_observation), actual_sha256=sha(body['observation']),
                observation_policy='identity', checked_before_model_call=True, model_calls_before_check=0,
                observation_budget=guard_budget) and body['observation'] == initial_observation,
                'Actual first request is not bound to retained initial observation')
        recorded = dict(selected); recorded.pop('axtree_full_txt', None)
        recorded['observation_record_source'] = 'actual_actor_request'
        payload = json.loads(actual[-1]['content']); recorded['axtree_txt'] = payload['observation']
        for key in ('url', 'observation_scope', 'observation_mode', 'observation_policy'):
            if key in payload: recorded[key] = payload[key]
        require(json.loads(before['content']) == recorded, 'Recorded trace observation differs from actual dispatched observation')
        reasons.append(reply['finish_reason'])
        row = dict(generation_index=index, browser_step_before=step_index, request_sha256=digest(actual),
                   input_tokens=generation['input_tokens'], budget=budget,
                   selected_policy=selected.get('observation_policy'), selected_mode=selected.get('observation_mode'),
                   raw_step_sha256=digest(steps[step_index]), history_sha256=digest(history),
                   actual_response_sha256=digest(reply), request_reconstructed=True)
        try:
            action, thought = protocol.parse(reply['text'], selected)
            validate_upload_action(action, [])
        except (ValueError, SyntaxError, TypeError) as error:
            require(response.get('action_payload') is None, 'Unparseable response became a browser action')
            limited = reply['finish_reason'] in ('length', 'max_tokens')
            history.append(dict(action=reply['text'], error='generation_output_limit' if limited else 'invalid_action_format'))
            observation = dict(observation, last_action_error='Invalid action format: ' + str(error)[:500])
            if limited:
                observation['last_action_error'] = ('Generation reached the output token limit before producing a valid complete action. '
                    'No browser action was executed. Return one complete JSON action within the output budget. ' + observation['last_action_error'])
            if memory is not None:
                memory.invalid_generation(index, observation['last_action_error'],
                    'generation_output_limit' if limited else 'invalid_action_format')
            row.update(action_executed=False, browser_step_after=step_index, parse_failure_retained=True)
        else:
            require(response.get('action_kind') == 'browsergym' and response.get('action_payload') == action,
                    'Executed action differs from actual model response')
            history.append(dict(thought=thought, action=action, url_before=observation.get('url')))
            history[-1]['targets'] = observed_targets(action, selected)
            if memory is not None:
                memory.action_started(index, action, selected)
            step_index += 1
            require(step_index < len(steps) and steps[step_index]['action'] == action, 'Actual browser action/next step missing')
            observation = deepcopy(steps[step_index]['observation'])
            if memory is not None:
                memory.action_returned(observation)
            history[-1].update(url_after=observation.get('url'), last_action_error=observation.get('last_action_error', ''))
            row.update(action_executed=True, browser_step_after=step_index, action=action,
                       next_step_sha256=digest(steps[step_index]))
        rows.append(row)
    require(len(steps) == step_index + 1, 'Unexplained actual browser steps')
    require(messages[-1]['role'] == 'user' and json.loads(messages[-1]['content']) ==
            dict(observation, observation_record_source='terminal_environment_observation_not_sent'),
            'Terminal environment observation differs or was misrepresented as dispatched')
    require(trace['generation_finish_reasons'] == reasons
            and trace['system_prompt'] == '\n'.join(m['content'] for m in generations[-1]['messages'] if m['role'] == 'system'),
            'Actual finish reasons or system prompt differs')
    if memory is not None:
        require(memory.audit() == trace['task_output']['actor_memory_evidence'],
                'Recorded Actor memory does not reconstruct from actual requests and browser returns')
    return dict(passed=True, requests_verified=len(rows), executed_actions=step_index, rows=rows,
                all_serialized_requests_reconstructed=True, actual_token_counts_recomputed=True,
                candidate_skill_bound=True, initial_guard_reconstructed=True,
                terminal_observation_not_counted_as_request=True,
                **({'actor_memory_policy': actor_memory_policy,
                    'actor_memory_reconstructed': True} if memory is not None else {}))
