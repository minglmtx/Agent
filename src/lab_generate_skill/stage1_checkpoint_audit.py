"""Read-only audit of a closed partial local run at its next missing operation.

Replay the actual policy and native validators using completed request receipts.
The audit never generates a response or executes an Actor. It establishes which
operation is missing; publishing a live continuation still requires a separate
source-bound authorization, including checks for an existing continuation.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tarfile

from .generator_sft import file_hash, fingerprint
from .local_stage1_driver import run_task
from .stage1_local import LocalRolloutValidator, read_pinned_json


class MissingOperation(Exception):
    def __init__(self, kind, key):
        self.boundary = dict(kind=kind, key=key)
        super().__init__(str(self.boundary))


def pin(path):
    return dict(path=str(Path(path).resolve()), sha256=file_hash(path))


def verify_archive(path, index):
    if file_hash(path) != index['archive_sha256']:
        raise ValueError('Closed archive bytes changed')
    seen = {}
    with tarfile.open(path, 'r:gz') as stream:
        for member in stream:
            if member.isdir():
                continue
            name = member.name.removeprefix('./')
            if (not member.isfile() or name in seen or name.startswith('/')
                    or '..' in Path(name).parts):
                raise ValueError('Invalid or duplicate archived member')
            data = stream.extractfile(member).read()
            seen[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            if seen[name] != index['members'].get(name):
                raise ValueError('Raw archive differs from its member inventory')
    if set(seen) != set(index['members']):
        raise ValueError('Archive member inventory is incomplete')
    return seen


def _regular_files(directory):
    entries = list(Path(directory).iterdir())
    if any(p.is_symlink() or not p.is_file() for p in entries):
        raise ValueError('Expected regular checkpoint files only')
    return entries


def audit_partial(*, base, source, capsule, validator, replay_directory,
                  model_name, generator_settings, teacher_settings,
                  teacher_messages, closure):
    """Audit a fresh source's contiguous prefix; imported lineage is separate.

    ``closure`` pins the original worker's started/termination/completed records,
    closed archive index, and archive. ``teacher_messages`` must reconstruct a
    retained Teacher request's exact encoding; it is never called for a missing
    request. The caller supplies the independently selected native validator.
    """
    if not isinstance(validator, LocalRolloutValidator):
        raise ValueError('An explicitly constructed native validator is required')
    base, replay_directory = Path(base).resolve(), Path(replay_directory).resolve()
    if (replay_directory.is_relative_to(base.parent)
            or base.parent.is_relative_to(replay_directory)):
        raise ValueError('Offline replay output must be outside the original run tree')
    local = validator.contract
    sid = source['source_task_id']
    expected = dict(source_task_id=sid, active_task_id=source['active_task_id'],
        runtime_task_id=source['runtime_task_id'], domain=source['domain'],
        capsule=capsule, native_contract=source['native_contract'],
        admission=source['admission'], contract_sha256=validator.contract_sha256)
    if (local['source_task_id'] != sid or local['task_id'] != source['active_task_id']
            or local['runtime_task_id'] != source['runtime_task_id']
            or local['domain'] != source['domain']
            or local['runtime_capsule_sha256'] != capsule['sha256']
            or validator.contract_ref != pin(base/'local-contract.json')):
        raise ValueError('Source identity, contract or runtime changed')
    for name in ('started', 'termination', 'completed', 'archive_index', 'archive'):
        ref = closure[name]
        if Path(ref['path']).resolve().parent != base.parent:
            raise ValueError('Closure evidence belongs to a different source run')
        if file_hash(ref['path']) != ref['sha256']:
            raise ValueError('Closure evidence changed')
    started = read_pinned_json(closure['started'])
    ended = read_pinned_json(closure['termination'])
    completed = read_pinned_json(closure['completed'])
    if started['source'] != sid or started['capsule'] != capsule:
        raise ValueError('Closed worker source or capsule changed')
    if (ended.get('confirmed') is not True or ended['group'].get('live_members') != []
            or ended['scope'].get('live_scratch_references') != []
            or ended['scope'].get('unreadable_same_uid_pids') != []):
        raise ValueError('Original worker closure is not proved')
    summary_ref = pin(base/'summary.json')
    summary = read_pinned_json(summary_ref)
    if (completed.get('local_workspace_retained') != started.get('workspace')
            or not isinstance(started.get('workspace'), str)
            or ended.get('returncode') != completed.get('returncode')
            or type(ended.get('returncode')) is not int
            or completed.get('source_summary') != summary
            or summary.get('source_task_id') != sid):
        raise ValueError('Worker closure, workspace or original source summary disagree')
    if completed.get('source_summary', {}).get('complete') is True:
        raise ValueError('Completed sources use completed-replay review')
    outer = verify_archive(closure['archive']['path'], read_pinned_json(closure['archive_index']))

    stage = base/'stage1'
    stage_files = _regular_files(stage)
    if (stage/'result.json').exists():
        raise ValueError('Completed result cannot be treated as a missing stage')
    order = [f'bootstrap-{i}-trajectory.json' for i in range(4)] + [
        f'teacher-{i}-trajectory.json' for i in range(1, 4)]
    names = {p.name for p in stage_files}
    retained = [name for name in order if name in names]
    if names != {'context.json', *retained} or retained != order[:len(retained)]:
        raise ValueError('Partial trajectories must be an exact contiguous prefix')
    evidence = base/'evidence'
    evidence_dirs = list(evidence.iterdir()) if evidence.exists() else []
    if (any(p.is_symlink() or not p.is_dir() for p in evidence_dirs)
            or {p.name for p in evidence_dirs} != {str(i) for i in range(len(retained))}):
        raise ValueError('Orphan or incomplete native evidence cannot be repeated')
    candidate_indices = set()
    wrappers = {name:set() for name in range(len(retained))}
    wrapper_names = {'executed-code.json', 'pre-inference-assets.json',
        'pre-inference-browser-config.json', 'scope.json', 'summary.json'}
    for name in outer:
        if name.startswith('candidate-'):
            match = re.fullmatch(r'candidate-(0|[1-9]\d*)/(.+)', name)
            if not match:
                raise ValueError('Closed episode source path changed')
            index, relative = int(match[1]), match[2]
            candidate_indices.add(index)
            if relative in wrapper_names:
                wrappers.setdefault(index,set()).add(relative)
            elif not relative.startswith(source['runtime_task_id']+'/'):
                raise ValueError('Unexpected file in closed Actor wrapper')
    if candidate_indices != set(range(len(retained))):
        raise ValueError('Closed run contains an unretained Actor attempt')
    if any(names != wrapper_names for names in wrappers.values()):
        raise ValueError('Incomplete ordinary Actor wrapper evidence')

    files = dict(context=pin(stage/'context.json'),
        trajectories=[pin(stage/name) for name in retained],
        requests=[pin(p) for p in sorted(_regular_files(base/'requests'))], result=None)
    ledger = {}
    for ref in files['requests']:
        value = read_pinned_json(ref)
        key = value.get('key')
        if (not isinstance(key, list) or len(key) != 2 or key[0] != sid
                or value.get('status') != 'complete' or value.get('paid') is not False
                or Path(ref['path']).name != fingerprint(key)+'.json'):
            raise ValueError('Incomplete, ambiguous or misbound model request')
        ledger[Path(ref['path']).name] = value

    members = 0
    for index, ref in enumerate(files['trajectories']):
        trace = read_pinned_json(ref)
        receipt_ref = trace['provenance']['local_execution_evidence']
        if receipt_ref != pin(evidence/str(index)/'receipt.json'):
            raise ValueError('Imported or unrelated evidence requires a lineage audit')
        receipt = read_pinned_json(receipt_ref)
        archive = read_pinned_json(receipt['archive'])
        inner = verify_archive(archive['path'], archive)
        prefix = f"candidate-{index}/{source['runtime_task_id']}/"
        subtree = {name.removeprefix(prefix):value for name,value in outer.items()
                   if name.startswith(prefix)}
        if subtree != inner:
            raise ValueError('Durable attempt differs from the entire closed Actor subtree')
        members += len(inner)

    replay_directory.mkdir(parents=True, exist_ok=False)
    for ref in [files['context'], *files['trajectories']]:
        (replay_directory/Path(ref['path']).name).write_bytes(Path(ref['path']).read_bytes())
    checked, requested = [], set()

    class RecordingValidator(LocalRolloutValidator):
        def __call__(self, trace, task, start, skill):
            result = super().__call__(trace, task, start, skill)
            checked.append(dict(trace_sha256=fingerprint(trace), success=result))
            return result

    recording = RecordingValidator(validator.contract_ref, review_execution=validator.review_execution)

    def read_response(messages, seed, key, settings):
        name = fingerprint([sid, key])+'.json'
        if name not in ledger:
            raise MissingOperation('model', key)
        value = ledger[name]
        expected_contract = fingerprint(dict(key=[sid, key], messages=messages,
            model=model_name, seed=seed, settings=settings))
        if value['contract'] != expected_contract:
            raise ValueError('Retained model request differs from the actual policy input')
        requested.add(name)
        return deepcopy(value['response'])

    def generate(messages, seed, temperature, key):
        settings = deepcopy(generator_settings)
        settings['temperature'] = temperature
        return read_response(messages, seed, key, settings)

    def teacher(messages, seed, key):
        if fingerprint([sid, key])+'.json' not in ledger:
            raise MissingOperation('model', key)
        return read_response(teacher_messages(messages, key), seed, key, teacher_settings)

    def rollout(task, start, skill, index):
        raise MissingOperation('actor', index)

    def forbidden(*args, **kwargs):
        raise ValueError('Retained initial context was not reused')

    try:
        run_task(dict(task_id=source['active_task_id'], domain=source['domain']),
            replay_directory, get_start=forbidden, retrieve=forbidden, generate=generate,
            rollout=rollout, teacher=teacher, purpose='engineering_pilot', local_validator=recording)
    except MissingOperation as stop:
        boundary = stop.boundary
    else:
        raise ValueError('Run can finalize offline; it is not a missing-operation continuation')
    if requested != set(ledger) or len(checked) != len(retained):
        raise ValueError('Unused model requests or Actor attempts invalidate the boundary')
    for ref in [files['context'], *files['trajectories'], *files['requests'], summary_ref,
                *closure.values()]:
        if file_hash(ref['path']) != ref['sha256']:
            raise ValueError('Original checkpoint changed during read-only audit')
    return dict(passed=True, safe_boundary_verified=True, next_operation=boundary,
        source_task_id=sid, checkpoint_mode='between_attempts', checkpoint_binding=expected,
        checkpoint_files=files, attempts_revalidated=len(checked),
        success_flags=[row['success'] for row in checked],
        actual_model_requests_verified=len(requested), archive_members_verified=members,
        closed_archive_members_verified=len(outer), unresolved_model_requests=0,
        unresolved_actor_episodes=0, checkpoint_import_authorized=False,
        closure=deepcopy(closure), original_summary=summary_ref,
        original_job_id=started.get('job_id'), original_workspace=started['workspace'],
        closure_layout='ordinary-source-wrapper-v1',
        authorization_limitation='Audit only. A live continuation requires separate authorization and exclusion of existing continuations.',
        new_actor_calls=0, new_model_calls=0, paid_api_calls=0, training_data=False)
