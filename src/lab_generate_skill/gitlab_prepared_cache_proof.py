"""Reuse a proved native cache baseline, with fresh checks after every reset.

The original Rails invocation and exact column transitions are retained once
in shared evidence storage. A reuse receipt is explicitly not an invocation.
"""
from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path

from . import evidence_store
from .gitlab_native_read_runtime import full_snapshot

VERSION = 'gitlab-prepared-cache-proof-v1'
KINDS = ('wiki', 'issue')
FILES = ('native-cache-initialization.json', 'native-cache-initialization-capture.json',
         'columns-before-native-initialization.json', 'columns-after-native-initialization.json',
         'native-cache-effect-verification.json')


def initializer(kind):
    if kind not in KINDS:
        raise ValueError('Only native wiki/issue cache initialization is supported')
    return importlib.import_module('gitlab_native_' + kind + '_cache_init')


def verify_phase(kind, files):
    module = initializer(kind)
    if set(files) != set(FILES):
        raise ValueError('Complete original native initialization evidence required')
    invoke = files['native-cache-initialization.json']
    if (invoke.get('command_returncode') != 0
            or invoke.get('stdout_native_begin_markers') != 1 or invoke.get('stdout_native_end_markers') != 1
            or invoke.get('rails_global_new_help_detected') is not False
            or invoke.get('application_entrypoint') != module.APPLICATION_ENTRYPOINT
            or invoke.get('ruby_sha256') != hashlib.sha256(Path(module.__file__).with_suffix('.rb').read_bytes()).hexdigest()):
        raise ValueError('Original successful native initializer invocation required')
    label = kind.upper()
    record = module.parse_result('LAB_NATIVE_' + label + '_CACHE_INIT_BEGIN\n'
        + json.dumps(invoke['native_record']) + '\nLAB_NATIVE_' + label + '_CACHE_INIT_END')
    capture = files['native-cache-initialization-capture.json']
    if (capture.get('status') != 'captured' or capture.get('capture_errors')
            or capture.get('primary_exception_type') or capture.get('native_record_complete') is not True
            or capture.get('actor_attempts') != 0 or capture.get('api_calls') != 0):
        raise ValueError('Complete native initialization capture required')
    cold = full_snapshot(capture['full_before']); after = full_snapshot(capture['full_after'])
    before_columns = files['columns-before-native-initialization.json']
    after_columns = files['columns-after-native-initialization.json']
    for columns, state in ((before_columns, cold), (after_columns, after)):
        if columns['row_count'] != state['projects']['rows'] or columns['columns'] != state['projects']['columns']:
            raise ValueError('Original project-column coverage differs from full state')
    effects = module.verify_effects(before_columns, after_columns, cold, after, record)
    if effects != files['native-cache-effect-verification.json']:
        raise ValueError('Original native initialization effects differ')
    return dict(name=kind, cold=cold, after=after, effects=effects)


def collect_original(kind, folder):
    folder = Path(folder)
    files = {}
    for name in FILES:
        path = folder/name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Actual regular initialization artifact required')
        files[name] = json.loads(path.read_text())
    verify_phase(kind, files)
    return files


def verify_origin(origin):
    if not isinstance(origin, dict) or list(origin) != list(KINDS):
        raise ValueError('Complete wiki then issue preparation required')
    phases = [verify_phase(kind, origin[kind]) for kind in KINDS]
    if phases[0]['after'] != phases[1]['cold']:
        raise ValueError('Original complete initialization chain differs')
    return phases


def verify_reuse(path, row):
    record = evidence_store.read(path)
    if (record.get('version') != VERSION or record.get('profile') != 'wiki_issue'
            or record.get('initializer_invoked') is not False
            or record.get('fresh_complete16_match') is not True):
        raise ValueError('Explicit freshly checked reuse receipt required')
    original = verify_origin(record['original_evidence'])
    actual = full_snapshot(record['current_full16'])
    columns = record['current_columns']
    if (actual != original[-1]['after']
            or columns != record['original_evidence']['issue']['columns-after-native-initialization.json']
            or actual != row['native_before_initialization'] or actual != row['protected_before']):
        raise ValueError('Fresh complete state does not reproduce original prepared baseline')
    phases = [dict(name=kind, cold=actual, after=actual,
        effects=initializer(kind).verify_effects(columns, columns, actual, actual, {'rows': []})) for kind in KINDS]
    if phases != row['native_initialization_effects'] or phases != record['phases']:
        raise ValueError('Reused initialization is not the proved no-change sequence')
    return phases


def reuse_sequence(site, folder):
    state = getattr(site, 'prepared_initialization', None)
    if state is None:
        return None
    if state.get('profile') not in ('wiki_issue','calendar_wiki_issue') or 'original_evidence' not in state:
        raise ValueError('Qualified complete prepared cache profile required')
    for kind in KINDS:
        if hashlib.sha256(Path(initializer(kind).__file__).read_bytes()).hexdigest() != state['initializers'][kind]['initializer_sha256']:
            raise ValueError('Prepared initializer implementation changed')
    original = verify_origin(state['original_evidence'])
    if original[-1]['after'] != state['prepared_after'] or original[0]['cold'] != state['cold_before']:
        raise ValueError('Prepared state no longer binds its original native proof')
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    from .gitlab_native_csv_probe import protected_snapshot_session
    import gitlab_project_column_hashes as columns_module
    actual = protected_snapshot_session(site, folder/'prepared-current-full16-progress.jsonl')
    columns = columns_module.snapshot(site)
    if (actual != state['prepared_after'] or columns != state['original_evidence']['issue']['columns-after-native-initialization.json']):
        raise ValueError('Current state differs from the original prepared baseline')
    phases = [dict(name=kind, cold=actual, after=actual,
        effects=initializer(kind).verify_effects(columns, columns, actual, actual, {'rows': []})) for kind in KINDS]
    # CPU controls for one source share its store. An ordinary actor defaults
    # to its own task directory so its independent checkpoint is self-contained;
    # no receipt points outside an already closed task archive.
    root = Path(getattr(site, 'native_cache_evidence_root', folder.parent)).resolve()
    temporary = Path(os.environ['TMPDIR']).resolve(strict=True)
    if not root.is_relative_to(temporary) or root == temporary or not folder.resolve().is_relative_to(root):
        raise ValueError('Prepared evidence must share one node-local archive tree')
    evidence_store.write(folder/'prepared-sequence.json', dict(version=VERSION, profile='wiki_issue',
        initializer_invoked=False, fresh_complete16_match=True, original_evidence=state['original_evidence'],
        current_full16=actual, current_columns=columns, phases=phases), root=root)
    return actual, actual, phases
