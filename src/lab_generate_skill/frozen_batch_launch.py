"""Create a small pinned Slurm bootstrap for an already prepared code capsule.

This only writes launch artifacts. It does not claim tasks, load models, create
sites, or submit jobs. Runtime publication remains a separate validation gate.
"""
import json
from pathlib import Path
import shlex

from .frozen_actor_capsule import sha, regular


def prepare(project, batch_file, capsule, output, *, root, python):
    project, batch_file, output = map(Path, (project, batch_file, output))
    batch = json.loads(batch_file.read_text())
    if batch.get('status') != 'ready' or not batch.get('workers'):
        raise ValueError('Ready nonempty actor batch required')
    for worker in batch['workers']:
        if sha(Path(worker['bundle']) / 'plan.json') != worker['plan_sha256']:
            raise ValueError('Worker plan changed before launch preparation')
    if sha(capsule['path']) != capsule['sha256']:
        raise ValueError('Frozen capsule changed before launch preparation')
    descriptor = json.loads(Path(capsule['path']).read_text())
    names = {'bootstrap.py': 'scripts/launch_frozen_site_batch.py',
             'extractor.py': 'src/lab_generate_skill/frozen_actor_capsule.py'}
    # Both bootstrap helpers must be the exact bytes in the reviewed capsule.
    for name in names.values():
        if descriptor['members'].get(name, {}).get('sha256') != sha(regular(project.resolve(), name)):
            raise ValueError('Launch helper does not match frozen runtime: ' + name)
    output.mkdir(parents=True, exist_ok=False)
    for target, source in names.items():
        (output / target).write_bytes((project / source).read_bytes())
    launcher, extractor = output / 'bootstrap.py', output / 'extractor.py'
    for target, source in names.items():
        if sha(output / target) != descriptor['members'][source]['sha256']:
            raise ValueError('Launch helper changed while copying')
    config = dict(version='frozen-site-batch-launch-v1', root=str(Path(root).resolve()),
                  batch=dict(path=str(batch_file.resolve()), sha256=sha(batch_file)),
                  capsule=capsule,
                  extractor=dict(path=str(extractor.resolve()), sha256=sha(extractor)))
    plan = output / 'launch.json'
    plan.write_text(json.dumps(config, sort_keys=True, indent=2) + '\n')
    # Slurm copies this script when submitted. Check the standalone bootstrap
    # before executing it; no dependency on the live project or setup-alex.sh.
    verifier = ('import hashlib,pathlib,sys\np=pathlib.Path(sys.argv[1]); b=p.read_bytes()\n'
                'if p.is_symlink() or hashlib.sha256(b).hexdigest()!=sys.argv[2]:\n'
                '    raise ValueError("Frozen bootstrap changed")\n'
                'sys.argv=[str(p),*sys.argv[3:]]\n'
                'exec(compile(b,str(p),"exec"),{"__name__":"__main__","__file__":str(p)})')
    command = [str(Path(python).resolve()), '-B', '-c', verifier, str(launcher.resolve()),
               sha(launcher), str(plan.resolve()), sha(plan)]
    script = output / 'site-actor-batches.sbatch'
    script.write_text('#!/bin/bash\n#SBATCH --job-name=site-actor-batches\n'
                      '#SBATCH --gres=gpu:1\n#SBATCH --cpus-per-task=8\n'
                      '#SBATCH --time=12:00:00\n#SBATCH --signal=B:TERM@600\n'
                      '#SBATCH --export=NONE\nset -euo pipefail\n'
                      'exec ' + shlex.join(command) + ' "${SLURM_ARRAY_TASK_ID:?Array index}"\n')
    return dict(script=str(script.resolve()), script_sha256=sha(script),
                plan=str(plan.resolve()), plan_sha256=sha(plan),
                bootstrap=str(launcher.resolve()), bootstrap_sha256=sha(launcher))
