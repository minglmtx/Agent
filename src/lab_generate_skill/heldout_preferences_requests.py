"""Exact already reviewed Read2 public-request replay; no preference answers."""
import json
from .runtime_profile import actor_protocol
from .action_history import observed_targets

def actor_goal(public):
    """Independently project the declared public goal, without runner imports."""
    if set(public) != {'task_id', 'domain', 'goal', 'start_path'}:
        raise ValueError('Only declared public task fields may enter the request')
    return public['goal']

def replay_requests(public, trace, generations, steps, *, answer_fields=None):
    """Reject inserted private fields, observations or scripted actions."""
    goal = actor_goal(public)
    if (trace['task_instruction'] != goal or trace.get('error')
            or trace['rounds'] != len(generations) or not generations
            or trace['provenance'].get('generated_skill_sha256') is not None):
        raise ValueError('Completed real Actor trajectory with the exact public goal required')
    messages = trace['messages']
    if len(messages) != 2 * len(generations) + 1:
        raise ValueError('Every generation needs its preceding observation and final observation')
    protocol = actor_protocol(answer_fields=answer_fields or None); history = []; step_index = 0
    output_budget = 4096 if answer_fields else 512
    for index, generation in enumerate(generations):
        before, response = messages[2 * index:2 * index + 2]
        if before['role'] != 'user' or response['role'] != 'assistant':
            raise ValueError('Observation/action order changed')
        observation = json.loads(before['content'])
        if (generation['status'] != 'complete' or generation['response']['text'] != response['content']
                or generation['seed'] != trace['seed'] + index
                or not 0 < generation['input_tokens'] <= 16384
                or generation['max_new_tokens'] != output_budget
                or generation['observation_budget']['truncated'] is not False):
            raise ValueError('Completed bounded generation without shortened AX required')
        raw = steps[step_index]['observation']
        tree_key = 'axtree_full_txt' if observation['observation_mode'] == 'full' else 'axtree_txt'
        if observation['axtree_txt'] != raw[tree_key] or observation['url'] != raw['url']:
            raise ValueError('Serialized observation differs from the actual browser step')
        if generation['messages'] != protocol.messages(goal, observation, history, skills=[]):
            raise ValueError('Actual request differs from public-task/browser/history reconstruction')
        action = response.get('action_payload')
        try:
            parsed, _ = protocol.parse(response['content'], observation)
        except (ValueError, SyntaxError, TypeError):
            if action is not None:
                raise ValueError('Invalid model response was converted to a browser action')
            history.append(dict(action=response['content'], error='generation_output_limit'
                if generation['response']['finish_reason'] in ('length', 'max_tokens') else 'invalid_action_format'))
            continue
        if action != parsed:
            raise ValueError('Executed action differs from actual model response')
        step_index += 1
        step = steps[step_index]
        if step['action'] != action:
            raise ValueError('Actual browser step differs from trajectory action')
        history.append(dict(action=action, url_before=observation['url'],
            targets=observed_targets(action, observation), url_after=step['observation']['url'],
            last_action_error=step['observation'].get('last_action_error', '')))
    if len(steps) != step_index + 1:
        raise ValueError('Unexplained extra browser steps')
    terminal = json.loads(messages[-1]['content'])
    if (messages[-1]['role'] != 'user' or terminal['url'] != steps[-1]['observation']['url']
            or trace['system_prompt'] != generations[-1]['messages'][0]['content']):
        raise ValueError('Final browser observation or actual system prompt differs')
    return dict(actual_generations=len(generations), executed_actions=step_index,
        all_serialized_requests_reconstructed=True, model_responses_bound_to_actions=True,
        skills_empty=True, source='actual generation messages, responses, trajectory and browser steps')
