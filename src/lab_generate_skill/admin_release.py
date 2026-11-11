"""One authoritative runtime: admissions from other code trees cannot be reused."""
import hashlib
import json
from pathlib import Path


def release_digest(files):
    return hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def verify_release(base):
    base=Path(base).resolve()
    metadata=json.loads((base/'release.json').read_text())
    files=metadata['files']
    if release_digest(files)!=metadata['release_id']:
        raise RuntimeError('Release manifest digest mismatch')
    expected_code={name for name in files if name.startswith('code/')}
    observed_code={str(path.relative_to(base)) for path in (base/'code').rglob('*')
                   if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc'}
    if expected_code!=observed_code:
        raise RuntimeError('Authoritative code file inventory changed')
    for name,expected in files.items():
        path=(base/name).resolve()
        path.relative_to(base)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise RuntimeError('Authoritative runtime changed: '+name)
    if (base/'admission-reuse.json').exists():
        raise RuntimeError('The authoritative runtime forbids cross-version admission reuse')
    return metadata


def verify_admission_release(base, directory, contract):
    base=Path(base).resolve();directory=Path(directory).resolve()
    if directory.parent!=base/'admission':
        raise RuntimeError('Admission is not from this authoritative runtime')
    metadata=json.loads((base/'release.json').read_text())
    if contract.get('release_id')!=metadata['release_id']:
        raise RuntimeError('Admission release does not match authoritative runtime')
