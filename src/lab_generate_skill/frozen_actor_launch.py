"""Bind a batch script to its actual frozen actor entry before allocation.

Job-name substitutions must never also rewrite filesystem paths. This check
does not start a website, rerun controls, load a model, or execute shell code.
"""
import hashlib
import json
from pathlib import Path
import re
import shlex


_ENTRY = re.compile(r'^export LAB_FROZEN_NATIVE_ENTRY=(.*)$', re.MULTILINE)


def bind_entry(script, entry):
    entry = Path(entry).resolve(strict=True)
    if not entry.is_file():
        raise ValueError('Frozen actor entry must be a file')
    if len(_ENTRY.findall(script)) != 1:
        raise ValueError('Exactly one literal frozen actor entry required')
    return _ENTRY.sub(lambda _: 'export LAB_FROZEN_NATIVE_ENTRY=' + shlex.quote(str(entry)), script)


def validate_launch(script_path, entry_manifest, manifest_sha256):
    script_path, entry_manifest = Path(script_path), Path(entry_manifest)
    raw = entry_manifest.read_bytes()
    sha = lambda body: hashlib.sha256(body).hexdigest()
    if sha(raw) != manifest_sha256:
        raise ValueError('Frozen entry manifest changed')
    files = json.loads(raw)
    if not isinstance(files, dict) or not files:
        raise ValueError('Nonempty frozen entry manifest required')
    for name, digest in files.items():
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('Frozen helper must be a direct child')
        if sha((entry_manifest.parent / name).read_bytes()) != digest:
            raise ValueError('Frozen helper changed: ' + name)
    matches = _ENTRY.findall(script_path.read_text())
    if len(matches) != 1:
        raise ValueError('Exactly one literal frozen actor entry required')
    tokens = shlex.split(matches[0])
    if len(tokens) != 1 or any(c in tokens[0] for c in '$`\n'):
        raise ValueError('Literal actor path required')
    entry = Path(tokens[0])
    expected = (entry_manifest.parent / 'run.py').resolve(strict=True)
    if not entry.is_absolute() or entry.resolve(strict=True) != expected:
        raise ValueError('Submitted actor entry differs from frozen run.py')
    if 'run.py' not in files or files.get(script_path.name) != sha(script_path.read_bytes()):
        raise ValueError('Both submitted script and actor entry must be frozen')
    # A valid main entry does not prove that an earlier bootstrap command exists.
    # Check the CUDA preflight too, before allocating or staging site images.
    gpu_helpers = []
    for line in script_path.read_text().splitlines():
        if line.lstrip().startswith('#') or 'gpu-preflight.py' not in line:
            continue
        tokens = shlex.split(line)
        paths = [token for token in tokens if 'gpu-preflight.py' in token]
        if len(paths) != 1 or any(c in paths[0] for c in '$`\n'):
            raise ValueError('Literal GPU preflight path required')
        path = Path(paths[0])
        expected_gpu = entry_manifest.parent / 'gpu-preflight.py'
        if not path.is_absolute() or path.resolve(strict=True) != expected_gpu.resolve(strict=True):
            raise ValueError('GPU preflight differs from frozen packet')
        if 'gpu-preflight.py' not in files or 'actor_gpu_preflight.py' not in files:
            raise ValueError('GPU preflight and its implementation must be frozen')
        gpu_helpers.append(str(path))
    if len(gpu_helpers) > 1:
        raise ValueError('GPU preflight declared more than once')
    return dict(entry=str(expected), manifest_sha256=manifest_sha256,
                gpu_preflight=gpu_helpers[0] if gpu_helpers else None,
                submitted_script_sha256=sha(script_path.read_bytes()), native_sites_started=0,
                actor_attempts=0, api_calls=0)


def validate_source_walltime(script_path, *, domain, watchdog_seconds,
                             rollout_timeout_seconds=360, bootstrap_seconds=120):
    """Reject allocations that cannot admit even the first ordinary attempt.

    Runtime estimates are not safety deadlines. Keep the existing per-source
    reserve and require both allocation and outer watchdog to accommodate it.
    """
    from .site_walltime_guard import source_budget
    if type(watchdog_seconds)is not int or watchdog_seconds<=0 or type(bootstrap_seconds)is not int or bootstrap_seconds<0:
        raise ValueError('Finite explicit watchdog/bootstrap seconds required')
    values=re.findall(r'^#SBATCH\s+--time(?:=|\s+)(\S+)\s*$',Path(script_path).read_text(),re.MULTILINE)
    if len(values)!=1:raise ValueError('One explicit Slurm time limit required')
    raw=values[0]
    if not re.fullmatch(r'(?:\d+-)?\d+(?::\d{1,2}){0,2}',raw):
        raise ValueError('Finite Slurm time limit required')
    day,clock=raw.split('-',1)if '-'in raw else('0',raw)
    parts=list(map(int,clock.split(':')))
    if '-'in raw:
        hours=parts[0];minutes=parts[1]if len(parts)>1 else 0;seconds=parts[2]if len(parts)>2 else 0
        if hours>23:raise ValueError('Invalid day-hour Slurm limit')
    elif len(parts)==3:hours,minutes,seconds=parts
    elif len(parts)==2:hours=0;minutes,seconds=parts
    else:hours=0;minutes=parts[0];seconds=0
    if seconds>59 or (len(parts)==3 or '-'in raw)and minutes>59:
        raise ValueError('Invalid Slurm clock fields')
    allocation=int(day)*86400+hours*3600+minutes*60+seconds
    required=source_budget(domain,rollout_timeout_seconds=rollout_timeout_seconds).required_seconds+bootstrap_seconds
    if min(allocation,watchdog_seconds)<required:
        raise ValueError(f'First source requires {required}s including bootstrap; allocation={allocation}s watchdog={watchdog_seconds}s')
    return dict(allocation_seconds=allocation,watchdog_seconds=watchdog_seconds,
                minimum_first_source_seconds=required,bootstrap_seconds=bootstrap_seconds,
                actor_attempts=0,websites_started=0)
