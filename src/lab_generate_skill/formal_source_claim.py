"""One durable execution owner per formal training source.

The caller must validate NativeTrainingValidator and the actual allocation first.
This helper neither grants API authorization nor recovers an interrupted run.
Completed and partial claims both require an explicit recovery decision; changing
the plan, output directory or job cannot create another automatic paid attempt.
"""
import hashlib
import json
import os
from pathlib import Path
import re


FORMAL_CLAIM_ROOT = Path('/anvme/workspace/r102bf10-lab-generate-skill/claims/sft-formal-native-stage1')
VERSION = 'formal-native-source-owner-v1'


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _reference(ref):
    _require(isinstance(ref, dict) and set(ref) == {'path', 'sha256'}, 'Exact file reference required')
    path = Path(ref['path'])
    _require(path.is_absolute() and str(path) == str(path.resolve()) and not path.is_symlink(),
             'Canonical non-symlink reference required')
    _require(isinstance(ref['sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', ref['sha256']),
             'SHA256 reference required')
    return path


def _read(ref):
    path = _reference(ref)
    data = path.read_bytes()
    _require(hashlib.sha256(data).hexdigest() == ref['sha256'], 'Formal release file changed')
    return json.loads(data)


def bound(source_plan_ref, authorization_ref, execution_job_id):
    """Read-only binding, also used by the independent closure reviewer."""
    plan, authorization = _read(source_plan_ref), _read(authorization_ref)
    _require(plan.get('purpose') == 'training' and plan.get('training_data') is True
             and plan.get('automatic_retry') is False and plan.get('construction_only') is False
             and isinstance(plan.get('complete_source_reviewer'), dict),
             'Released formal source plan required')
    _reference(plan['complete_source_reviewer'])
    _require(isinstance(plan.get('sources'), list) and len(plan['sources']) == 1,
             'Exactly one formal source required')
    source = plan['sources'][0]
    source_id = source.get('source_task_id')
    _require(isinstance(source_id, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', source_id),
             'Unsafe source identity')
    _require(all(isinstance(source.get(key), str) and source[key].strip()
                 for key in ('active_task_id', 'runtime_task_id')), 'Source task identity missing')
    _require(isinstance(execution_job_id, str) and re.fullmatch(r'[1-9][0-9]*', execution_job_id),
             'Exact Slurm execution job required')
    _require(authorization.get('version') == 'native-stage1-training-authorization-v1'
             and authorization.get('source_plan') == source_plan_ref
             and authorization.get('source_task_ids') == [source_id]
             and authorization.get('user_api_authorized') is True
             and authorization.get('local_pilot_reported') is True,
             'Explicit matching formal authorization required')
    _reference(plan['capsule'])
    result = Path(plan['result_directory'])
    _require(result.is_absolute() and str(result) == str(result.resolve()),
             'Canonical formal result directory required')
    root = FORMAL_CLAIM_ROOT
    _require(root.is_absolute() and root.resolve() == root and not root.is_symlink(),
             'Canonical formal claim root required')
    owner = dict(version=VERSION, phase='formal-native-stage1',
                 source_task_id=source_id, active_task_id=source['active_task_id'],
                 runtime_task_id=source['runtime_task_id'], source_plan=source_plan_ref,
                 authorization=authorization_ref, capsule=plan['capsule'],
                 job_id=execution_job_id, result_directory=str(result), automatic_retry=False)
    return owner, root / source_id


def claim(source_plan_ref, authorization_ref, execution_job_id):
    owner, directory = bound(source_plan_ref, authorization_ref, execution_job_id)
    directory.parent.mkdir(parents=True, exist_ok=True)
    # mkdir is the single atomic winner. Leave the directory in place even if
    # writing the owner fails: absence of a receipt never proves no API request.
    directory.mkdir(exist_ok=False)
    with (directory / 'owner.json').open('x') as stream:
        json.dump(owner, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    for path in (directory, directory.parent):
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return owner


def require_claim(source_plan_ref, authorization_ref, execution_job_id):
    owner, directory = bound(source_plan_ref, authorization_ref, execution_job_id)
    _require(directory.is_dir() and not directory.is_symlink() and directory.resolve() == directory,
             'Original formal claim missing or redirected')
    path = directory / 'owner.json'
    _require(path.is_file() and not path.is_symlink()
             and {p.name for p in directory.iterdir()} == {'owner.json'},
             'Incomplete or unexpected formal claim evidence')
    try:
        recorded = json.loads(path.read_text())
    except (ValueError, OSError) as error:
        raise ValueError('Incomplete formal claim receipt') from error
    _require(recorded == owner, 'Formal claim belongs to another plan or job')
    return owner
