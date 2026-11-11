"""Source-bound test engineering inputs, never expert demonstrations.

Only observations preceding the first assistant action are exposed. Selection
uses trace identity, not outcome, terminal URL, or successful historical actions.
This module establishes provenance, not live initial-state equivalence.
"""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

VERSION = 'heldout-initial-state-v1'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def source_id(task):
    return (task.get('source_task_id') or task['task_id']).split('--', 1)[0]


def first_frame(task, locator):
    """Verify a single indexed source record; never scan its enclosing archive."""
    offset, length = locator['byte_offset'], locator['byte_length']
    if (type(offset) is not int or offset < 0 or type(length) is not int
            or not 0 < length <= 64 * 1024 * 1024):
        raise ValueError('Invalid source record byte range')
    with Path(locator['source_file']).open('rb') as stream:
        stream.seek(offset)
        raw = stream.read(length)
    if len(raw) != length or hashlib.sha256(raw).hexdigest() != locator['line_sha256']:
        raise ValueError('Source record bytes changed')
    trace = json.loads(raw)
    if (trace.get('trace_id') != locator['trace_id']
            or trace.get('task_id') != source_id(task)
            or trace.get('domain') != task['domain']
            or trace.get('task_instruction') != task.get('original_task_instruction', task['task_instruction'])):
        raise ValueError('Source record task/trace/domain/goal mismatch')
    observation = None
    message_index = None
    for index, message in enumerate(trace.get('messages', [])):
        role = message.get('role')
        if role in ('assistant', 'tool'):
            break
        if role != 'user':
            continue
        content = message.get('content')
        try:
            candidate = json.loads(content) if isinstance(content, str) else content
        except (TypeError, ValueError):
            continue
        if isinstance(candidate, dict) and isinstance(candidate.get('axtree'), str):
            observation = {k: candidate.get(k) for k in
                           ('axtree', 'last_action', 'last_action_error')}
            message_index = index
            break
    if observation is None:
        raise ValueError('No observation before the first assistant action')
    lines = observation['axtree'].splitlines()
    root = lines[0].strip() if lines else ''
    if not re.match(r'^(?:\[\d+\]\s+)?RootWebArea\b', root):
        raise ValueError('Initial observation lacks a root document')
    match = re.search(r"\burl=(['\"])(.*?)\1\s*$", root)
    if not match:
        raise ValueError('Initial root document URL missing')
    url = match[2]
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('Initial root URL is not an ordinary website URL')
    path = (parsed.path or '/') + ('?' + parsed.query if parsed.query else '')
    path += '#' + parsed.fragment if parsed.fragment else ''
    provenance = trace.get('provenance', {})
    declared = provenance.get('actual_start_url')
    if declared and provenance.get('start_state_verified') is True and declared != url:
        raise ValueError('Verified declared start disagrees with first observation')
    return dict(trace_id=trace['trace_id'], source_locator={k: locator[k] for k in
                ('trace_id', 'source_file', 'byte_offset', 'byte_length', 'line_sha256')},
                message_index=message_index, original_url=url, start_path=path,
                observation=observation, observation_sha256=fingerprint(observation),
                source_node_url=provenance.get('source_node_url'),
                initial_action_error=bool(observation.get('last_action_error')),
                live_equivalence_verified=False)


def audit_task(task):
    records = task.get('records', [])
    ids = [r.get('trace_id') for r in records]
    if not ids or any(not isinstance(t, str) or not t for t in ids) or len(set(ids)) != len(ids):
        raise ValueError('Distinct original trace records required')
    frames, errors = [], []
    for locator in sorted(records, key=lambda r: r['trace_id']):
        try:
            frames.append(first_frame(task, locator))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(dict(trace_id=locator.get('trace_id'), error=str(exc)))
    # Never silently substitute a healthy or successful trace for the fixed one.
    selected_id = min(ids)
    selected = next((f for f in frames if f['trace_id'] == selected_id), None)
    variants = sorted({f['start_path'] for f in frames})
    blockers = []
    if errors:
        blockers.append('source_record_error')
    if selected is None:
        blockers.append('selected_initial_frame_unavailable')
    elif selected['initial_action_error']:
        blockers.append('selected_initial_action_error')
    state = dict(version=VERSION, source_task_id=source_id(task), domain=task['domain'],
                 goal=task['task_instruction'], split='test',
                 selected_trace_id=selected_id,
                 selection_policy='lexicographically_first_trace_id_before_outcome_inspection',
                 start_path=selected['start_path'] if selected else None,
                 initial_observation_sha256=selected['observation_sha256'] if selected else None,
                 recorded_start_paths=variants, initial_state_variants=len({
                     f['observation_sha256'] for f in frames}),
                 source_record_errors=errors, blockers=blockers,
                 provenance_status='blocked' if blockers else 'first_frame_bound',
                 live_initialization_status='not_verified',
                 contract_status='pending', controls_status='not_run',
                 actor_status='not_run', independent_review_status='pending',
                 evaluation_ready=False, eligible_for_training=False,
                 distill_skill=False, add_to_skill_bank=False)
    state['baseline_fingerprint'] = fingerprint(dict(
        version=VERSION, task={k: task.get(k) for k in
            ('task_id', 'source_task_id', 'domain', 'task_instruction', 'original_task_instruction')},
        selected_trace_id=selected_id, frames=[{k: f[k] for k in
            ('trace_id', 'source_locator', 'observation_sha256', 'start_path')} for f in frames],
        errors=errors))
    return state, frames


def changed_sources(current, previous):
    """Per-source baseline delta only; this does not authorize skipping controls."""
    old = {r['source_task_id']: r for r in previous}
    new = {r['source_task_id']: r for r in current}
    if len(old) != len(previous) or len(new) != len(current):
        raise ValueError('Duplicate source identity in engineering inventory')
    return dict(added=sorted(new.keys() - old.keys()), removed=sorted(old.keys() - new.keys()),
                changed=sorted(k for k in new.keys() & old.keys()
                               if new[k]['baseline_fingerprint'] != old[k]['baseline_fingerprint']),
                unchanged=sorted(k for k in new.keys() & old.keys()
                                 if new[k]['baseline_fingerprint'] == old[k]['baseline_fingerprint']))
