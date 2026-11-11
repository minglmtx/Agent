"""Native artifact initialization and raw-evidence helpers, retaining prepared-cache reuse."""
from copy import deepcopy

import hashlib

import base64

import json

import os

from pathlib import Path

import re

from urllib.parse import quote

VERSION = 'gitlab-existing-families-full-native-candidate-v1'

READ_KINDS = {'document', 'tag_commit'}

KINDS = READ_KINDS | {'repository_file'}

def _read(path):
    return json.loads(Path(path).read_text())

def _artifact_file(folder, name):
    folder = Path(folder).resolve(); p = folder / name
    if not p.is_file() or p.is_symlink() or folder not in p.resolve().parents:
        raise ValueError('Original private evidence file required: ' + name)
    return p

def initialize_baseline(site, directory):
    from lab_generate_skill.gitlab_prepared_cache_proof import reuse_sequence
    prepared = reuse_sequence(site, directory)
    if prepared is not None: return prepared
    import gitlab_native_wiki_cache_init as wiki
    import gitlab_native_issue_cache_init as issue
    phases = []; first = previous = None
    for name, module in (('wiki', wiki), ('issue', issue)):
        cold, after, effects = module.initialize(site, Path(directory) / name)
        if first is None: first = cold
        if previous is not None and cold != previous:
            raise ValueError('Complete native initialization chain changed between collectors')
        phases.append({'name': name, 'cold': cold, 'after': after, 'effects': effects})
        previous = after
    return first, previous, phases

def verify_initialization(directory, row):
    prepared = Path(directory) / "cache-initialization" / "prepared-sequence.json"
    if prepared.exists():
        from lab_generate_skill.gitlab_prepared_cache_proof import verify_reuse
        return verify_reuse(prepared, row)
    import gitlab_native_wiki_cache_init as wiki
    import gitlab_native_issue_cache_init as issue
    from lab_generate_skill.gitlab_native_read_runtime import full_snapshot
    phases = row['native_initialization_effects']
    if not isinstance(phases, list) or [v.get('name') for v in phases] != ['wiki', 'issue']:
        raise ValueError('Complete exact native initialization sequence required')
    previous = row['native_before_initialization']
    for phase, module, marker in zip(phases, (wiki, issue), ('WIKI', 'ISSUE')):
        folder = Path(directory) / 'cache-initialization' / phase['name']
        full_snapshot(phase['cold']); full_snapshot(phase['after'])
        if phase['cold'] != previous:
            raise ValueError('Original complete initialization chain differs')
        invocation = _read(_artifact_file(folder, 'native-cache-initialization.json'))
        if (invocation.get('command_returncode') != 0 or invocation.get('stdout_native_begin_markers') != 1
                or invocation.get('stdout_native_end_markers') != 1 or invocation.get('rails_global_new_help_detected') is not False
                or invocation.get('application_entrypoint') != module.APPLICATION_ENTRYPOINT
                or invocation.get('ruby_sha256') != hashlib.sha256(Path(module.__file__).with_suffix('.rb').read_bytes()).hexdigest()):
            raise ValueError('Actual successful pinned native initialization command required')
        record = module.parse_result('LAB_NATIVE_' + marker + '_CACHE_INIT_BEGIN\n' + json.dumps(invocation['native_record']) + '\nLAB_NATIVE_' + marker + '_CACHE_INIT_END')
        capture = _read(_artifact_file(folder, 'native-cache-initialization-capture.json'))
        if (capture.get('status') != 'captured' or capture.get('capture_errors') or capture.get('primary_exception_type')
                or capture.get('native_record_complete') is not True or capture.get('actor_attempts') != 0 or capture.get('api_calls') != 0
                or capture['full_before'] != phase['cold'] or capture['full_after'] != phase['after']):
            raise ValueError('Original complete cold initialization capture differs')
        columns_before = _read(_artifact_file(folder, 'columns-before-native-initialization.json'))
        columns_after = _read(_artifact_file(folder, 'columns-after-native-initialization.json'))
        for by_columns, raw in ((columns_before, phase['cold']), (columns_after, phase['after'])):
            if by_columns['row_count'] != raw['projects']['rows'] or by_columns['columns'] != raw['projects']['columns']:
                raise ValueError('Every native project column/row must be included')
        effects = module.verify_effects(columns_before, columns_after, phase['cold'], phase['after'], record)
        if effects != phase['effects'] or effects != _read(_artifact_file(folder, 'native-cache-effect-verification.json')):
            raise ValueError('Exact native initialization effects differ')
        previous = phase['after']
    if previous != row['protected_before']:
        raise ValueError('Complete final initialized baseline differs')
    return phases

from . import native_artifact_page_lifetime as page_lifetime

"""Original native closed-worker proof check; does not start a producer."""
from copy import deepcopy

import hashlib

import json

from pathlib import Path

import re





def load(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError('Original regular raw JSON required')
    return json.loads(path.read_text())

def close_receipt(worker):
    row = load(Path(worker) / 'worker-cleanup.json')
    if (not re.fullmatch('[0-9a-f]{64}', row.get('fresh_instance_id', ''))
            or row.get('state_exists_after_close') is not False
            or row.get('services_stopped') is not True or row.get('remaining_process_ids') != []
            or row.get('native_site_exit_completed') is not True
            or row.get('all_port_handles_closed') is not True
            or row.get('api_calls') != 0 or row.get('actor_attempts') != 0):
        raise ValueError('Actual complete native cleanup must precede source admission')
    state = row.get('original_state_path')
    if not isinstance(state, str) or not Path(state).is_absolute() or hashlib.sha256(state.encode()).hexdigest() != row['fresh_instance_id']:
        raise ValueError('Cold identity must bind the original actual native state path')
    return row
