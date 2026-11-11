"""Private, byte-verified staging of an immutable image for CPU experiments.

This does not change the default website runtime. Callers own the temporary
directory lifetime. Never share mutable website data or reuse partial copies.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import time

_VERIFIED_RUNTIME_COPIES = set()


def runtime_image(source, *, environ=None):
    """Opt-in node-local immutable image; never changes the default snapshot.

    The manifest is produced by stage_image in this Slurm job. Each Python
    process checks the local bytes once and checks file identity on every use.
    Mutable application data remain separate for every isolated instance.
    """
    env = os.environ if environ is None else environ
    source = Path(source)
    name = env.get('LAB_GITLAB_STAGED_IMAGE_MANIFEST')
    if not name:
        return source
    if not env.get('SLURM_JOB_ID') or not env.get('TMPDIR'):
        raise ValueError('Staged runtime image requires its original Slurm allocation')
    temporary = Path(env['TMPDIR']).resolve(strict=True)
    manifest = Path(name).resolve(strict=True)
    if not manifest.is_relative_to(temporary):
        raise ValueError('Image manifest must be inside the current node-local allocation')
    record = json.loads(manifest.read_text())
    if record.get('slurm_job_id') != env['SLURM_JOB_ID'] or record.get('byte_verified') is not True:
        raise ValueError('Image proof belongs to a different job or is unverified')
    if Path(record['source']) != source.absolute():
        raise ValueError('Image proof is for a different benchmark snapshot')
    target = Path(record['destination']).resolve(strict=True)
    if not target.is_relative_to(temporary) or target == temporary:
        raise ValueError('Staged image must be inside current node-local allocation')
    info = target.stat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o400 or info.st_uid != os.getuid():
        raise ValueError('Staged image must be a private read-only regular file owned by this user')
    current = identity(target)
    if list(current) != record.get('destination_identity') or current[2] != record.get('bytes'):
        raise ValueError('Staged image changed after byte verification')
    key = (str(target), current, record.get('sha256'))
    if key not in _VERIFIED_RUNTIME_COPIES:
        checksum = hashlib.sha256()
        with target.open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024**2), b''): checksum.update(block)
        if checksum.hexdigest() != record.get('sha256') or identity(target) != current:
            raise ValueError('Staged runtime image checksum mismatch')
        _VERIFIED_RUNTIME_COPIES.add(key)
    return target


def identity(path):
    s = Path(path).stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def stage_image(source, destination, *, progress=None):
    source, destination = Path(source).resolve(strict=True), Path(destination)
    before = identity(source)
    if not stat.S_ISREG(source.stat().st_mode):
        raise ValueError('Image source must be a regular file')
    if destination.exists() or destination.is_symlink():
        raise ValueError('Staged image destination must be new')
    if not destination.parent.is_dir():
        raise ValueError('Caller must provide a private staging directory')
    if shutil.disk_usage(destination.parent).free < before[2] + 1024**3:
        raise ValueError('Insufficient node-local space for image staging')
    partial = destination.with_name(destination.name + '.partial')
    started = time.monotonic(); size = 0; last_report = 0; copied = hashlib.sha256(); owned = False
    try:
        with source.open('rb') as incoming, partial.open('xb') as outgoing:
            owned = True
            os.chmod(partial, 0o600)
            while True:
                block = incoming.read(8 * 1024**2)
                if not block:
                    break
                outgoing.write(block); copied.update(block); size += len(block)
                if progress and size - last_report >= 256 * 1024**2:
                    progress({'phase':'copy','bytes':size,'total_bytes':before[2],'seconds':time.monotonic()-started})
                    last_report = size
            outgoing.flush(); os.fsync(outgoing.fileno())
        if size != before[2] or identity(source) != before:
            raise RuntimeError('Source image changed during staging')
        copy_seconds = time.monotonic() - started
        check_started = time.monotonic(); checked = hashlib.sha256()
        with partial.open('rb') as incoming:
            for block in iter(lambda: incoming.read(8 * 1024**2), b''):
                checked.update(block)
        if checked.digest() != copied.digest() or identity(source) != before:
            raise RuntimeError('Image copy verification failed or source changed')
        os.chmod(partial, 0o400)
        os.replace(partial, destination)
        result = {'source':str(source),'destination':str(destination),'source_identity':before,
                  'bytes':size,'sha256':copied.hexdigest(),'copy_seconds':copy_seconds,
                  'verify_seconds':time.monotonic()-check_started,'byte_verified':True}
        if progress:
            progress({'phase':'verified','bytes':size,'sha256':result['sha256']})
        return result
    except BaseException:
        if owned:
            partial.unlink(missing_ok=True)
        raise
