"""Offline review of actual persisted controls; never grants task admission.

Small receipts bind the raw archive members instead of copying full database
snapshots into another report. Every branch is rescored from its native state.
"""
import hashlib
import json
from urllib.parse import urlsplit

from . import gitlab_persisted_goal_runtime as runtime
from .gitlab_persisted_mutation import evaluate
from .site_navigation_rules import valid_initial_page


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def review_control(contract, base, name, *, raw, page, initial_page, summary,
                   events, actions, reader=None):
    """Rescore one recorded branch; no inference from a claimed pass flag."""
    if name not in {'no_op', 'unsaved', 'positive'}:
        raise ValueError('Unknown native control branch')
    if (raw.get('native_spec') != base['native_spec'] or raw.get('initial') != base['initial']
            or raw.get('capture_errors') != []):
        raise ValueError('Control object/precondition or native capture differs')
    for key in ('initial_guard', 'final_guard'):
        runtime.full_snapshot({k:v for k,v in raw[key].items() if k != 'visibility_relation'})
    guard = runtime.protection_integrity(raw['initial_guard'], raw['final_guard'],
                                        raw['native_spec'], raw['account_id'])
    guard = guard and runtime.refs_equal(raw['initial_refs'], raw['final_refs'],
                        raw['native_spec'], raw['initial'], raw['final'])
    result = evaluate(raw['native_spec'], raw['initial'], raw['final'],
                      protected_state_unchanged=guard)
    expected = 'success' if name == 'positive' else 'failure'
    if (not guard or raw.get('integrity') is not True or result['status'] != expected
            or summary.get('passed') is not True or summary.get('integrity') is not True
            or summary.get('status') != result['status']):
        raise ValueError('Recorded control conflicts with independently checked native state')
    url = urlsplit(initial_page.get('url', ''))
    origin = f'{url.scheme}://{url.netloc}'
    if (url.scheme not in {'http', 'https'} or not url.netloc
            or initial_page['url'] != origin + contract['start_path']
            or not valid_initial_page(page, site_origin=origin)):
        raise ValueError('Initial task path or terminal document differs')
    if (not isinstance(events, list) or events[:3] != ['prepare', 'attach', 'observe_initial']
            or events[-2:] != ['capture_terminal', 'score_terminal'] or 'record' not in events
            or events.count('capture_terminal') != 1 or events.count('score_terminal') != 1):
        raise ValueError('One ordinary terminal-only lifecycle required')
    declaration = contract['gitlab_persisted_goal']['declaration']
    if (name == 'positive' and declaration.get('ui') == 'upload'
            and not any(isinstance(a, str) and a.startswith('upload_file(') for a in actions)):
        raise ValueError('Saved native upload lacks an ordinary upload action')
    if reader is not None:
        if (reader.get('closed') is not True or reader.get('process_exited') is not True
                or reader.get('private_directory_removed') is not True
                or reader.get('forced_stop') is not False or reader.get('returncode') != 0
                or not reader.get('requests') or summary.get('reader_closed_before_score') is not True):
            raise ValueError('Attempt-owned native reader did not close cleanly')
    return {
        'name': name, 'status': result['status'], 'checks': result['checks'],
        'initial_native_sha256': digest(raw['initial']),
        'initial_guard_sha256': digest(raw['initial_guard']),
        'initial_refs_sha256': digest(raw['initial_refs']),
        'spec_sha256': digest(raw['native_spec']),
        'ordinary_lifecycle_verified': True, 'native_integrity_verified': True,
        'reader_cleanup_verified': reader is not None,
        'recorded_actions': sum(isinstance(a, str) and bool(a) for a in actions),
    }


def require_same_baseline(controls):
    """Controls from different jobs may be combined only on identical states."""
    if not controls:
        raise ValueError('Actual controls required')
    for key in ('initial_native_sha256', 'initial_guard_sha256', 'initial_refs_sha256', 'spec_sha256'):
        values = [c.get(key) for c in controls]
        if any(not isinstance(v, str) or not runtime.SHA.fullmatch(v) for v in values) or len(set(values)) != 1:
            raise ValueError('Control baselines differ: ' + key)
