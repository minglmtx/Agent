"""Persist completed interaction before fallible private terminal evaluation."""
from copy import deepcopy
from .io_utils import atomic_write_json


def save_unscored_rollout(directory, trace):
    """Keep raw environment output separate from an explicitly unscored trace.

    Never use the open-ended browser environment's reward as task success.
    A later evaluator may replace trajectory.json; rollout-raw.json is retained.
    These files are diagnostic outputs, never added to actor observations.
    """
    atomic_write_json(directory / 'rollout-raw.json', trace)
    pending = deepcopy(trace)
    pending['evaluation_outcome'] = 'unknown'
    pending['evaluation_feedback'] = {'status': 'pending_terminal_evaluation'}
    output = pending.setdefault('task_output', {})
    output['openended_environment_reward'] = output.get('reward')
    output['reward'] = None
    pending['eligible_training_sample'] = False
    atomic_write_json(directory / 'trajectory.json', pending)
    atomic_write_json(directory / 'rollout-checkpoint.json', {
        'interaction_complete': True, 'terminal_evaluation_complete': False,
        'rounds': trace.get('rounds'), 'finish_reason': trace.get('finish_reason'),
        'raw_file': 'rollout-raw.json', 'api_calls': 0,
    })
