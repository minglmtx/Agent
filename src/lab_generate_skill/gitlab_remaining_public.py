"""Native callback port; source controls and scoring preserved."""
from copy import deepcopy

_PRIVATE_KEYS = {'private_reference', 'expected_answer', 'ground_truth', 'controls', 'judgment',
                 'full_before', 'full_after', 'source_trace_ids', 'hidden_checks', 'reference_values'}

import hashlib

import json

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def _required_values(value, path='public_parameters'):
    if value is None:
        raise ValueError('Unresolved required public task parameter: ' + path)
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key or key in _PRIVATE_KEYS:
                raise ValueError('Named public parameters required')
            _required_values(item, path + '.' + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _required_values(item, path + '[' + str(index) + ']')
    elif type(value) not in (str, int, float, bool):
        raise ValueError('JSON public task parameters required')

def public_input(case, *, bound_input_sha256=None):
    value = case.get('public_task_input')
    allowed = {'goal', 'public_parameters', 'required_unresolved_public_parameters'}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError('Explicit public task input required; private fields are not accepted')
    if (not isinstance(value.get('goal'), str) or not value['goal'].strip()
            or value['goal'] != case.get('goal')
            or not isinstance(value.get('public_parameters'), dict)
            or value['public_parameters'] != case.get('public_parameters')):
        raise ValueError('Public input differs from the declared task and parameters')
    if value.get('required_unresolved_public_parameters'):
        raise ValueError('Materialize and publicly declare task parameters before inference')
    _required_values(value['public_parameters'])
    family = case.get('family', '')
    params = value['public_parameters']
    if family.startswith('gitlab_native_read.') or family in ('gitlab_grouped_goal.tag_commit', 'gitlab_persisted_goal.repository_file'):
        if not isinstance(params.get('project'), str) or not params['project'].strip():
            raise ValueError('Required public native repository project missing')
    encoded = canonical(value).encode()
    if bound_input_sha256 is not None and hashlib.sha256(encoded).hexdigest() != bound_input_sha256:
        raise ValueError('Public task bytes changed after source binding')
    return deepcopy(value)

def render(case, *, bound_input_sha256=None):
    value = public_input(case, bound_input_sha256=bound_input_sha256)
    text = value['goal']
    if value['public_parameters']:
        text += '\n\nTask-supplied parameters:\n' + json.dumps(
            value['public_parameters'], ensure_ascii=False, sort_keys=True,
            indent=2, allow_nan=False)
    return text

def append_parameters(case, public_goal):
    """Keep the normal runner's answer protocol and add supplied parameters."""
    if not isinstance(public_goal, str):
        raise ValueError('Normal public goal must be text')
    if 'public_task_input' not in case:
        return public_goal
    value = public_input(case)
    if value['goal'] not in public_goal:
        raise ValueError('Normal public goal omitted the declared task')
    if not value['public_parameters']:
        return public_goal
    return public_goal + '\n\nTask-supplied parameters:\n' + json.dumps(
        value['public_parameters'], ensure_ascii=False, sort_keys=True,
        indent=2, allow_nan=False)
