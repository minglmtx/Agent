"""Resolve an Admin evaluator from its admitted binding, never a domain default.

The caller supplies the bind/actor_goal functions from the pinned executable
capsule. This module does not load callbacks from records or permit retries.
Historical diagnosis is not a rewritten contract or an import authorization.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(ref):
    require(isinstance(ref, dict) and set(ref) == {'path', 'sha256'}, 'Expected explicit file pin')
    path = Path(ref['path'])
    require(path.is_absolute(), 'Absolute evidence path required')
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'Pinned evidence changed')
    return json.loads(raw)


def resolve_admitted_admin(source, *, bind, actor_goal):
    """All source IDs use the same original native binding mechanism."""
    require(source.get('domain') == 'shopping_admin', 'Expected Admin source')
    native, admission, row = (read(source[k]) for k in ('native_contract', 'admission', 'source_row'))
    sid = source['source_task_id']
    require(native.get('source_task_id') == row.get('source_task_id') == admission.get('task_id') == sid,
            'Admitted source identity differs')
    require(row.get('domain') == 'shopping_admin', 'Registered row domain differs')
    require(admission.get('passed') is True and admission.get('binding') == native,
            'Native contract differs from admitted binding')
    require(native.get('status') == 'ready_for_single_attempt', 'Native binding is not ready')
    rebound = bind(deepcopy(row), deepcopy(admission['state']))
    require(rebound == native, 'Frozen registry rebinding differs from admitted contract')
    version = native.get('evaluator_version')
    require(isinstance(version, str) and bool(version.strip()), 'Missing admitted evaluator version')
    goal = actor_goal(deepcopy(native))
    require(goal == row.get('goal'), 'Public goal differs from registered source')
    runtime = native.get('runtime_task_id', sid)
    require(source['runtime_task_id'] == row.get('runtime_task_id', sid) == runtime,
            'Admitted runtime task identity differs')
    return dict(version='admitted-admin-evaluator-binding-v1', source_task_id=sid,
                runtime_task_id=runtime, public_goal=goal, evaluator_version=version,
                native_contract=deepcopy(source['native_contract']),
                admission=deepcopy(source['admission']), source_row=deepcopy(source['source_row']))


def require_declared_evaluator(source, resolution):
    require(source['source_task_id'] == resolution['source_task_id'], 'Resolution is for another source')
    require(source.get('evaluator_version') == resolution['evaluator_version'],
            'Declared evaluator differs from admitted evaluator')


def corrected_source(source, resolution):
    """Return a prospective source value; never modify the frozen original."""
    require(source['source_task_id'] == resolution['source_task_id'], 'Resolution is for another source')
    for key in ('native_contract', 'admission', 'source_row'):
        require(source[key] == resolution[key], 'Resolution input pins differ')
    value = deepcopy(source)
    value['evaluator_version'] = resolution['evaluator_version']
    require_declared_evaluator(value, resolution)
    return value


def historical_mismatch(*, plan, source, local, local_ref, receipt, trace,
                        resolution, dispatcher_version):
    """Describe only the proven domain-default wiring error, not any mismatch."""
    require(plan.get('sources') == [source] and plan.get('purpose') == 'engineering_pilot'
            and plan.get('training_data') is False and plan.get('automatic_retry') is False,
            'Original source plan is not an exclusive no-retry pilot')
    require(read(local_ref) == local, 'Original local contract changed')
    require(source['source_task_id'] == resolution['source_task_id'], 'Resolution source mismatch')
    for key in ('native_contract', 'admission', 'source_row'):
        require(source[key] == resolution[key], 'Resolution input pins differ')
    expected = dict(source_task_id=source['source_task_id'], task_id=source['active_task_id'],
                    runtime_task_id=source['runtime_task_id'], domain=source['domain'],
                    public_goal=resolution['public_goal'], runtime_capsule_sha256=plan['capsule']['sha256'])
    require(all(local.get(k) == value for k, value in expected.items()), 'Original local source/plan binding differs')
    require(local.get('output_purpose') == 'engineering_pilot' and local.get('teacher_mode') == 'local_replacement',
            'Original purpose differs')
    old, actual = local.get('evaluator_version'), resolution['evaluator_version']
    require(old == source.get('evaluator_version') == dispatcher_version and actual != old,
            'Not the diagnosed dispatcher-default mismatch')
    for key in ('source_task_id', 'task_id', 'runtime_task_id', 'runtime_capsule_sha256', 'website_snapshot_id'):
        require(receipt.get(key) == local.get(key), 'Original receipt identity differs: ' + key)
    require(receipt.get('contract_sha256') == local_ref['sha256'], 'Original receipt contract differs')
    provenance = trace.get('provenance', {})
    require((provenance.get('mode'), provenance.get('outcome_source'), provenance.get('local_evaluator_version'))
            == ('online', 'local_task_evaluator', actual), 'Actual evaluator provenance differs')
    require(trace.get('task_id') == source['runtime_task_id'] and trace.get('domain') == source['domain']
            and trace.get('task_instruction') == resolution['public_goal'], 'Actual trace source/goal differs')
    require(provenance.get('website_snapshot_id') == local['website_snapshot_id'], 'Actual snapshot differs')
    return dict(version='historical-admin-evaluator-wiring-diagnosis-v1',
                original_evaluator_version=old, admitted_actual_evaluator_version=actual,
                original_contract=deepcopy(local_ref), corrected_source=corrected_source(source, resolution),
                old_contract_still_rejected=True, original_evidence_modified=False,
                checkpoint_import_authorized=False, continuation_authorized=False,
                source_complete=False, export_ready=False, formal_training_targets=0)
