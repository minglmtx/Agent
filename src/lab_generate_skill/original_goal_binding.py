"""Unchanged original identities for optional terminal-only protocols."""
from copy import deepcopy
import hashlib
import json
from urllib.parse import urlsplit

def local_path(value):
    part = urlsplit(value)
    return (part.path or '/') + ('?' + part.query if part.query else '') + ('#' + part.fragment if part.fragment else '')

def binding(contract):
    names = ('source_task_id', 'goal', 'start_path', 'recorded_start_paths', 'source_trace_ids')
    if (not isinstance(contract.get('source_task_id'), str) or not contract['source_task_id']
            or not isinstance(contract.get('goal'), str) or not contract['goal']
            or contract.get('original_goal') != contract['goal']
            or not isinstance(contract.get('recorded_start_paths'), list) or not contract['recorded_start_paths']
            or contract.get('start_path') != contract['recorded_start_paths'][0]
            or not isinstance(contract.get('source_trace_ids'), list) or not contract['source_trace_ids']):
        raise ValueError('Unchanged original goal, first start and complete traces required')
    for path in contract['recorded_start_paths']:
        u = urlsplit(path)
        if not isinstance(path, str) or not path.startswith('/') or path.startswith('//') or u.scheme or u.netloc or '\\' in path:
            raise ValueError('Exact local original start paths required')
    return {name: deepcopy(contract[name]) for name in names}

def fingerprint(contract):
    return hashlib.sha256(json.dumps({k: v for k, v in contract.items() if k != 'admission_result'},
                                    sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def require_local_origin(value):
    u = urlsplit(value)
    if (u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost') or u.port is None
            or u.username is not None or u.password is not None
            or u.path not in ('', '/') or u.query or u.fragment):
        raise ValueError('Actual isolated loopback website origin required')
    return value

def require_original_binding(contract, original, inventory):
    binding(contract)
    if not isinstance(original, dict) or {k: v for k, v in contract.items() if k != 'admission_result'} != original:
        raise ValueError('Original contract changed after controls')
    if (not isinstance(inventory, dict) or inventory.get('task_id') != contract['source_task_id']
            or inventory.get('domain') != contract['domain'] or inventory.get('heldout_quarantine') is not False
            or inventory.get('goal') != contract['goal']
            or inventory.get('source_trace_ids') != contract['source_trace_ids']
            or [local_path(x) for x in inventory.get('recorded_start_urls', [])] != contract['recorded_start_paths']):
        raise ValueError('Authoritative original source/goal/start/traces differ')
