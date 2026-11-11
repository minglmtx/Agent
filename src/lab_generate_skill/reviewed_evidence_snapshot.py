"""Read byte-identical historical publication metadata without restoring defaults.

Only mutable publication pointers may be relocated. Runtime code, contracts,
results and artifact hashes cannot be overridden by this mechanism.
"""
from pathlib import Path
import hashlib
import json
from .provider_review_catalog import identity

POINTERS = ('task-dataset-current.json', 'data-active-scope.json', 'site-runtime-current.json')


def validate_snapshots(rows, project):
    if not isinstance(rows, list) or not rows:
        raise ValueError('Explicit publication snapshots required')
    allowed = {str(Path(project) / 'configs' / name) for name in POINTERS}
    # A node-local capsule moves executable files, but historical proof pins
    # still name the publication's original project. Accept that origin only
    # when its declaration is itself bound to verified frozen package bytes.
    project = Path(project)
    declaration = project / '.lab-reviewed-frozen-runtime-file-sha256.json'
    if declaration.exists():
        if declaration.is_symlink():
            raise ValueError('Regular frozen runtime declaration required')
        pins = json.loads(declaration.read_text())
        config = project / 'configs/site-runtime-current.json'
        if (config.is_symlink() or not config.is_file()
                or hashlib.sha256(config.read_bytes()).hexdigest() != pins.get('configs/site-runtime-current.json')):
            raise ValueError('Frozen publication origin must be pinned')
        origin = json.loads(config.read_text()).get('production_project')
        if not isinstance(origin, str) or not Path(origin).is_absolute() or '..' in Path(origin).parts:
            raise ValueError('Absolute published project origin required')
        allowed.update(str(Path(origin) / 'configs' / name) for name in POINTERS)
    seen = set()
    for row in rows:
        key = (row['original_path'], row['sha256'])
        if key in seen or row['original_path'] not in allowed:
            raise ValueError('Only distinct publication metadata snapshots are supported')
        seen.add(key)
        p = Path(row['snapshot_path'])
        if not p.is_absolute() or str(p) in allowed:
            raise ValueError('Separate absolute historical evidence path required')
        before = identity(p)
        if hashlib.sha256(p.read_bytes()).hexdigest() != row['sha256'] or identity(p) != before:
            raise ValueError('Publication snapshot must have exactly the historical bytes')


def evidence_path(owner, pin):
    rows = owner.config.get('_evidence_snapshots', [])
    matches = [r for r in rows if r['original_path'] == pin['path']
               and r['sha256'] == pin['sha256']]
    if len(matches) > 1:
        raise ValueError('Ambiguous historical publication evidence')
    return Path(matches[0]['snapshot_path'] if matches else pin['path'])
