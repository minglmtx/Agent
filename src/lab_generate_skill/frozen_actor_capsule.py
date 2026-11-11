"""One verified code capsule per batch; expand only on node-local storage.

No website data, model weights, checkpoints, or API credentials are discovered
automatically. The publisher supplies the exact project-relative runtime files.
"""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import tarfile

MANIFEST = '.lab-reviewed-frozen-runtime-file-sha256.json'
MAX_TOTAL = 2 * 1024**3
MAX_MEMBER = 64 * 1024**2


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def safe_name(name):
    if not isinstance(name, str) or not name:
        raise ValueError('Safe relative runtime member required')
    path = PurePosixPath(name)
    if (not path.parts or path.is_absolute()
            or '..' in path.parts or '\\' in name or str(path) != name
            or name == MANIFEST):
        raise ValueError('Safe relative runtime member required')
    return name


def regular(root, name):
    path = root / safe_name(name)
    if (path.is_symlink() or not path.is_file() or root not in path.resolve().parents
            or any(p.is_symlink() for p in path.parents if p != root and root in p.parents)):
        raise ValueError('Regular contained runtime file required: ' + name)
    return path


def build(project, output, names):
    root = Path(project).resolve()
    names = sorted(names)
    if not names or len(set(names)) != len(names):
        raise ValueError('Distinct runtime members required')
    paths = {name: regular(root, name) for name in names}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    archive = output / 'runtime.tgz'
    members = {}
    total = 0
    with tarfile.open(archive, 'w:gz') as tar:
        for name, path in paths.items():
            if path.stat().st_size > MAX_MEMBER:
                raise ValueError('Runtime capsule member size exceeded')
            raw = path.read_bytes()
            total += len(raw)
            if len(raw) > MAX_MEMBER or total > MAX_TOTAL:
                raise ValueError('Runtime capsule size exceeded')
            digest = hashlib.sha256(raw).hexdigest()
            entry = tarfile.TarInfo(name)
            entry.size = len(raw)
            entry.mode = 0o600
            tar.addfile(entry, io.BytesIO(raw))
            members[name] = dict(bytes=len(raw), sha256=digest)
    # A concurrent edit never yields a mixed successful publication.
    for name, path in paths.items():
        if sha(regular(root, name)) != members[name]['sha256']:
            raise ValueError('Runtime changed while freezing: ' + name)
    descriptor = dict(version='frozen-actor-capsule-v1', archive=str(archive.resolve()),
                      archive_sha256=sha(archive), members=members, total_bytes=total)
    file = output / 'capsule.json'
    file.write_text(json.dumps(descriptor, sort_keys=True, indent=2) + '\n')
    return dict(path=str(file.resolve()), sha256=sha(file))


def extract(descriptor_path, expected_sha256, destination):
    descriptor_path = Path(descriptor_path)
    if descriptor_path.is_symlink() or sha(descriptor_path) != expected_sha256:
        raise ValueError('Frozen capsule descriptor changed')
    config = json.loads(descriptor_path.read_text())
    if config.get('version') != 'frozen-actor-capsule-v1' or not config.get('members'):
        raise ValueError('Explicit nonempty frozen capsule required')
    archive = Path(config['archive'])
    if not archive.is_absolute() or archive.is_symlink() or sha(archive) != config['archive_sha256']:
        raise ValueError('Frozen code archive changed')
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    seen = set()
    total = 0
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            name = safe_name(member.name)
            if not member.isfile() or name in seen or name not in config['members']:
                raise ValueError('Unexpected frozen runtime member')
            total += member.size
            if member.size < 0 or member.size > MAX_MEMBER or total > MAX_TOTAL:
                raise ValueError('Frozen runtime size exceeded')
            raw = tar.extractfile(member).read(member.size + 1)
            if config['members'][name] != dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) or len(raw) != member.size:
                raise ValueError('Frozen runtime member changed')
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open('xb') as stream:
                os.chmod(path, 0o600)
                stream.write(raw)
            seen.add(name)
    if seen != set(config['members']) or total != config['total_bytes']:
        raise ValueError('Frozen capsule is incomplete')
    (root / MANIFEST).write_text(json.dumps({k: v['sha256'] for k, v in config['members'].items()}, sort_keys=True) + '\n')
    return root
