"""Exact source identity for original goals and explicit training derivatives.

The authoritative inventory retains the original goal and every recorded start
and trace. Determinization is a versioned mapping, never benchmark equivalence.
No alias, reservation or heldout checks are relaxed by this helper.
"""
from copy import deepcopy
import hashlib
import json
from urllib.parse import urlsplit


def local_path(value):
    if not isinstance(value, str):
        raise ValueError('Recorded URL/path must be text')
    part = urlsplit(value)
    return (part.path or '/') + ('?' + part.query if part.query else '') + (
        '#' + part.fragment if part.fragment else '')


def exact_local_path(value):
    if not isinstance(value, str):
        raise ValueError('Local start must be text')
    parsed = urlsplit(value)
    if (not value.startswith('/') or value.startswith('//') or parsed.scheme
            or parsed.netloc or '\\' in value or '\x00' in value):
        raise ValueError('Exact local start path required')
    return value


def _revision(record, old_key, new_key, old, new):
    if (not isinstance(record, dict) or record.get(old_key) != old
            or record.get(new_key) != new or not record.get('version')
            or not isinstance(record.get('reason'), str) or not record['reason'].strip()):
        raise ValueError('Explicit versioned source-to-training revision required')
    flags = [v for k, v in record.items() if k.startswith('equivalent_to_original')]
    if flags != [False]:
        raise ValueError('A changed goal/start must not claim original equivalence')


def binding(contract):
    fields = ('source_task_id', 'domain', 'original_goal', 'goal', 'start_path',
              'recorded_start_urls', 'recorded_start_paths', 'source_trace_ids',
              'task_text_changed', 'goal_revision', 'start_revision')
    if (not isinstance(contract, dict) or not isinstance(contract.get('domain'), str)
            or not isinstance(contract.get('source_task_id'), str) or not contract['source_task_id']
            or any(not isinstance(contract.get(k), str) or not contract[k].strip()
                   for k in ('original_goal', 'goal'))
            or contract.get('heldout_quarantine') is not False):
        raise ValueError('Unquarantined original source and goal mapping required')
    for key in ('recorded_start_urls', 'recorded_start_paths', 'source_trace_ids'):
        values = contract.get(key)
        if (not isinstance(values, list) or not values
                or any(not isinstance(v, str) or not v for v in values)):
            raise ValueError('All source starts and trace IDs required')
    if list(map(local_path, contract['recorded_start_urls'])) != contract['recorded_start_paths']:
        raise ValueError('Recorded source URL/path mapping differs')
    for path in contract['recorded_start_paths'] + [contract['start_path']]:
        exact_local_path(path)
    changed = contract['goal'] != contract['original_goal']
    if contract.get('task_text_changed') is not changed:
        raise ValueError('Task text change declaration differs')
    if changed:
        _revision(contract.get('goal_revision'), 'original_goal', 'derived_goal',
                  contract['original_goal'], contract['goal'])
    elif contract.get('goal_revision'):
        raise ValueError('An unchanged goal must not have a spurious revision')
    original_start = contract['recorded_start_paths'][0]
    if contract['start_path'] != original_start:
        _revision(contract.get('start_revision'), 'original_start', 'derived_start',
                  original_start, contract['start_path'])
    elif contract.get('start_revision'):
        raise ValueError('An unchanged start must not have a spurious revision')
    return {key: deepcopy(contract[key]) for key in fields if key in contract}


def fingerprint(contract):
    return hashlib.sha256(json.dumps({k: v for k, v in contract.items() if k != 'admission_result'},
        sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def require_source_binding(contract, original_contract, inventory, *, domain):
    result = binding(contract)
    if (contract.get('domain') != domain or not isinstance(original_contract, dict)
            or {k: v for k, v in contract.items() if k != 'admission_result'} != original_contract):
        raise ValueError('Exact control contract/domain changed after CPU validation')
    if (not isinstance(inventory, dict) or inventory.get('task_id') != contract['source_task_id']
            or inventory.get('domain') != domain or inventory.get('heldout_quarantine') is not False
            or inventory.get('goal') != contract['original_goal']
            or inventory.get('source_trace_ids') != contract['source_trace_ids']
            or inventory.get('recorded_start_urls') != contract['recorded_start_urls']
            or list(map(local_path, inventory.get('recorded_start_urls', [])))
               != contract['recorded_start_paths']):
        raise ValueError('Authoritative original source/goal/all starts/all traces differ')
    return result
