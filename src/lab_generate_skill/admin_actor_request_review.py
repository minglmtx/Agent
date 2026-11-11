"""Pure saved-request reconstruction; no model, browser, evaluator or claim."""
from copy import deepcopy
import hashlib
import json


def require(ok, message):
    if not ok: raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _reconstruct(*, trace, steps, generations, skill, goal, task_id, snapshot_id,
                model_path, protocol, count_tokens, fit_messages, observed_targets,
                validate_upload_action, skill_fingerprint, initial_guard, initial_observation,
                domain, check_initial_guard, query=False, upload_files=()):
    """Replay the frozen ordinary request pipeline against raw step observations.

    Policy selection, message formatting, line budgeting, parsing and observed
    targets are original capsule callables. Only the small recorded-history loop
    is explicit here, including parse-failure observation/error transitions.
    """
    require(trace.get('error') is None and trace['sample_status'] == 'completed', 'Completed ordinary trace required')
    require(trace['task_id'] == task_id and trace['domain'] == domain and trace['task_instruction'] == goal
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
    require(type(query) is bool and (bool(protocol.answer_fields) if query else protocol.answer_fields is None),
            'Declared Admin query answer schema differs')
    from .runtime_profile import PROFILE
    output_budget = PROFILE['query_max_output_tokens'] if query else 512
    messages = trace['messages']
    require(len(messages) == 2 * len(generations) + 1
            and [r['turn'] for r in messages] == list(range(len(messages))), 'Complete recorded message sequence required')
    skills = [json.dumps(skill, ensure_ascii=False)]
    history = []; step_index = 0; observation = deepcopy(steps[0]['observation']); rows = []; reasons = []
    require(observation.get('available_files', []) == list(upload_files),
            'Initial task upload resources differ from declared local assets')
    require(provenance['start_url'] == observation['url'], 'Initial source URL differs')
    for index, generation in enumerate(generations):
        before, response = messages[2 * index:2 * index + 2]
        require(before['role'] == 'user' and response['role'] == 'assistant', 'Request/response ordering differs')
        require(generation['status'] == 'complete' and generation['seed'] == expected_seed + index
                and generation['max_new_tokens'] == output_budget, 'Actual bounded completed generation differs')
        selected = protocol.prepare_observation(goal, observation, history, token_counter=count_tokens,
                                               action_description=None, skills=skills)
        requested = protocol.messages(goal, selected, history, action_description=None, skills=skills)
        actual, budget = fit_messages(requested, count_tokens, 16384)
        require(actual == generation['messages'], 'Actual dispatched messages do not reconstruct at generation ' + str(index))
        require(budget == generation['observation_budget'] and budget['input_tokens'] == generation['input_tokens']
                and 0 < generation['input_tokens'] <= 16384, 'Actual observation budget/token count differs')
        reply = generation['response']
        require(reply['text'] == response['content'] and reply['prompt_tokens'] == count_tokens(actual),
                'Actual response or backend prompt token count differs')
        require(type(reply['completion_tokens']) is int and 0 <= reply['completion_tokens'] <= output_budget,
                'Actual completion token budget differs')
        if index == 0:
            # InitialObservationGuard runs beneath MeasuredActor. Recompute its
            # second no-op fit and exact observed-initial binding too.
            guarded, guard_budget = fit_messages(actual, count_tokens, 16384)
            require(guarded == actual, 'Initial guard changed actual dispatched request')
            body = json.loads(guarded[-1]['content'])
            require(body['observation'] == initial_observation, 'Actual initial observation differs')
            check_initial_guard(initial_guard, guarded, guard_budget)
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
            validate_upload_action(action, upload_files)
        except (ValueError, SyntaxError, TypeError) as error:
            require(response.get('action_payload') is None, 'Unparseable response became a browser action')
            limited = reply['finish_reason'] in ('length', 'max_tokens')
            history.append(dict(action=reply['text'], error='generation_output_limit' if limited else 'invalid_action_format'))
            observation = dict(observation, last_action_error='Invalid action format: ' + str(error)[:500])
            if limited:
                observation['last_action_error'] = ('Generation reached the output token limit before producing a valid complete action. '
                    'No browser action was executed. Return one complete JSON action within the output budget. ' + observation['last_action_error'])
            row.update(action_executed=False, browser_step_after=step_index, parse_failure_retained=True)
        else:
            require(response.get('action_kind') == 'browsergym' and response.get('action_payload') == action,
                    'Executed action differs from actual model response')
            history.append(dict(thought=thought, action=action, url_before=observation.get('url')))
            history[-1]['targets'] = observed_targets(action, selected)
            step_index += 1
            require(step_index < len(steps) and steps[step_index]['action'] == action, 'Actual browser action/next step missing')
            observation = deepcopy(steps[step_index]['observation'])
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
    return dict(passed=True, requests_verified=len(rows), executed_actions=step_index, rows=rows,
                all_serialized_requests_reconstructed=True, actual_token_counts_recomputed=True,
                candidate_skill_bound=True, initial_guard_reconstructed=True,
                terminal_observation_not_counted_as_request=True)


def reconstruct(*, prepared_context, **kwargs):
    """Reconstruct every Admin request and the complete first-message guard."""
    from admin_sft_request_guard import compare_initial_messages
    require(kwargs.get('actor_memory_policy') is None, 'Admin retains its existing Actor history policy')
    kwargs.pop('actor_memory_policy', None)
    controls = kwargs.pop('public_controls', None)
    if controls is not None:
        prepared_users = [m for m in prepared_context['messages'] if m['role'] == 'user']
        require(len(prepared_users) == 1 and kwargs['initial_observation'] ==
                json.loads(prepared_users[0]['content'])['observation'],
                'Declared initial observation differs from the complete prepared request')
        # The full guard below binds prepared and actual requests using their
        # witnessed controls. The replay loop must compare the raw candidate
        # observation to its own dispatched bytes, retaining transient names.
        actual_users = [m for m in kwargs['generations'][0]['messages'] if m['role'] == 'user']
        require(len(actual_users) == 1, 'One actual initial Admin user message required')
        kwargs['initial_observation'] = json.loads(actual_users[0]['content'])['observation']
    def check_initial_guard(guard, messages, budget):
        if controls is None:
            proof = compare_initial_messages(prepared_context, messages, kwargs['skill'])
        else:
            from admin_declarative_request_guard import compare_initial_messages as compare_declarative
            require(set(controls) == {'prepared', 'actual'}, 'Complete public control binding required')
            proof = compare_declarative(prepared_context, messages, kwargs['skill'],
                                         controls['prepared'], controls['actual'])
        require(all(guard.get(k) == v for k, v in proof.items())
                and guard.get('checked_before_model_call') is True
                and guard.get('model_calls_before_check') == 0
                and guard.get('observation_budget') == budget,
                'Admin complete first-request guard differs from actual dispatch')
    return _reconstruct(domain='shopping_admin', check_initial_guard=check_initial_guard, **kwargs)
