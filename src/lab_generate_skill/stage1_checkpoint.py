"""Explicit, hash-bound Stage-1 imports; completed work is never repeated.

Only an independently reviewed manifest can authorize import. The manifest
lists every retained request and trajectory and distinguishes a completed
replay from a safe boundary before a missing attempt. Incomplete requests or
started-but-unscored Actor episodes cannot authorize an automatic retry.
"""
from pathlib import Path
import re

from .generator_sft import file_hash
from .stage1_local import read_pinned_json

TRAJECTORY = re.compile(r"^(bootstrap-(\d+)|teacher-([1-3]))-trajectory\.json$")


def import_checkpoint(checkpoint_ref, directory, *, source, capsule, contract_ref):
    manifest = read_pinned_json(checkpoint_ref)
    review = read_pinned_json(manifest['review'])
    expected = dict(source_task_id=source['source_task_id'],
                    active_task_id=source['active_task_id'],
                    runtime_task_id=source['runtime_task_id'], domain=source['domain'],
                    capsule=capsule, native_contract=source['native_contract'],
                    admission=source['admission'], contract_sha256=contract_ref['sha256'])
    if manifest.get('version') != 'stage1-checkpoint-import-v1' or manifest.get('binding') != expected:
        raise ValueError('Checkpoint source, scope, runtime or baseline changed')
    if review.get('passed') is not True or review.get('source_task_id') != source['source_task_id']:
        raise ValueError('An independent passed review of this source is required')
    if (manifest.get('paid_api_calls') != 0 or manifest.get('training_data') is not False
            or manifest.get('unresolved_model_requests') != 0
            or manifest.get('unresolved_actor_episodes') != 0):
        raise ValueError('An unresolved request or Actor episode cannot be retried')
    mode = manifest.get('mode')
    if mode not in ('completed_replay', 'between_attempts'):
        raise ValueError('Checkpoint must declare its exact safe resume boundary')
    if (review.get('checkpoint_import_authorized') is not True
            or review.get('checkpoint_binding') != expected
            or review.get('checkpoint_files') != manifest.get('files')):
        raise ValueError('Every checkpoint import requires explicit file-bound authorization')
    files = manifest['files']
    if set(files) != {'context', 'trajectories', 'requests', 'result'}:
        raise ValueError('Checkpoint file categories changed')
    context = read_pinned_json(files['context'])
    if context.get('local_reward_contract_sha256') != contract_ref['sha256']:
        raise ValueError('Checkpoint context is bound to another contract')
    if len(context['refs']) != 6:
        raise ValueError('Checkpoint must retain exactly six retrieved references')
    trajectories, requests = [], []
    names = set()
    for ref in files['trajectories']:
        name = Path(ref['path']).name
        match = TRAJECTORY.fullmatch(name)
        if not match or name in names:
            raise ValueError('Checkpoint trajectory name is invalid or duplicated')
        names.add(name)
        trajectories.append((ref, read_pinned_json(ref)))
    order = ['bootstrap-%d-trajectory.json' % i for i in range(4)] + [
        'teacher-%d-trajectory.json' % i for i in range(1, 4)]
    if [Path(ref['path']).name for ref, _ in trajectories] != order[:len(trajectories)]:
        raise ValueError('Retained Actor attempts must be a contiguous ordered prefix')
    if not 0 <= len(trajectories) <= 7:
        raise ValueError('Checkpoint exceeded the four-candidate/three-Teacher policy')
    request_names = set()
    for ref in files['requests']:
        name = Path(ref['path']).name
        value = read_pinned_json(ref)
        if (name in request_names or value.get('status') != 'complete'
                or value.get('paid') is not False
                or value.get('key', [None])[0] != source['source_task_id']):
            raise ValueError('Only complete source-bound local requests can be imported')
        request_names.add(name)
        requests.append((ref, value))
    result = read_pinned_json(files['result']) if files['result'] else None
    if mode == 'completed_replay':
        if (result is None or len(trajectories) < 5
                or review.get('attempts_revalidated') != len(trajectories)
                or result.get('local_reward_contract_sha256') != contract_ref['sha256']
                or len(result.get('attempts', [])) != len(trajectories)):
            raise ValueError('Completed replay requires all independently reviewed attempts')
        for attempt, (ref, _) in zip(result['attempts'], trajectories):
            if attempt['validation'] != dict(trajectory_path=ref['path'], trajectory_sha256=ref['sha256']):
                raise ValueError('Result refers to a different retained trajectory')
    elif result is not None:
        raise ValueError('A completed result cannot use partial-continuation mode')
    # Validate all files before writing any import. Exclusive creation protects
    # concurrent workers and prevents a started output from being retried.
    destination = Path(directory)
    for subdir, rows in [('stage1', [(files['context'], context)] + trajectories +
                        ([(files['result'], result)] if result else [])), ('requests', requests)]:
        target = destination / subdir
        target.mkdir(exist_ok=False)
        for ref, _ in rows:
            output = target / Path(ref['path']).name
            with output.open('xb') as stream:
                stream.write(Path(ref['path']).read_bytes())
            if file_hash(output) != ref['sha256']:
                raise ValueError('Checkpoint copy did not preserve bytes')
    return dict(context=context, mode=mode, retained_attempts=len(trajectories),
                retained_requests=len(requests), manifest=manifest, result=result)
