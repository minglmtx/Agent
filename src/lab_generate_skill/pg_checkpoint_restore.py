"""Restore a native PG basebackup and check its byte custody in one read.

The destination is exclusive node-local storage. Nothing may start PostgreSQL
until both archives pass; a partially extracted directory is never a baseline.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import time


class DigestReader:
    def __init__(self, stream, progress=None, budget_seconds=3600):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.count = 0
        self.progress = progress
        self.started = self.last = time.monotonic()
        self.deadline = self.started + budget_seconds

    def read(self, size=-1):
        data = self.stream.read(size)
        self.digest.update(data)
        self.count += len(data)
        now = time.monotonic()
        if now > self.deadline:
            raise TimeoutError('Checkpoint read exceeded its one-hour phase budget')
        if self.progress and now - self.last >= 30:
            self.progress(self.count, now - self.started)
            self.last = now
        return data


def extract_verified(archive, destination, expected, progress=None, budget_seconds=3600):
    archive, destination = Path(archive), Path(destination)
    if archive.is_symlink() or archive.stat().st_size != expected['bytes']:
        raise ValueError('Checkpoint archive size or file type changed')
    destination.mkdir(parents=True, exist_ok=True)
    seen = set()
    started = time.monotonic()
    with archive.open('rb') as stream:
        reader = DigestReader(stream, progress=progress, budget_seconds=budget_seconds)
        with tarfile.open(fileobj=reader, mode='r|', bufsize=1024 * 1024) as bundle:
            for member in bundle:
                relative = PurePosixPath(member.name)
                if (relative.is_absolute() or '..' in relative.parts
                        or relative.as_posix() in seen
                        or not (member.isfile() or member.isdir())):
                    raise ValueError('Unsafe or duplicate physical backup member')
                seen.add(relative.as_posix())
                target = destination / relative.as_posix()
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True, mode=0o700)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    # Exclusive creation also prevents archive alias overwrites.
                    with target.open('xb') as output, bundle.extractfile(member) as data:
                        shutil.copyfileobj(data, output, length=1024 * 1024)
                    os.chmod(target, 0o600)
        while reader.read(8 * 1024 * 1024):
            pass
        if reader.count != expected['bytes'] or reader.digest.hexdigest() != expected['sha256']:
            raise ValueError('Physical backup bytes changed during restore')
    return {'file': archive.name, 'bytes': reader.count,
            'sha256': reader.digest.hexdigest(), 'members': len(seen),
            'seconds': time.monotonic() - started}


def restore_checkpoint(receipt_path, destination, progress=None, budget_seconds=3600):
    started = time.monotonic()
    receipt_path, destination = Path(receipt_path), Path(destination)
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('version') == 'map28-native-pg11-closed-checkpoint-v2':
        if len(receipt['archives']) != 1 or receipt['archives'][0]['file'] != 'base.tar':
            raise ValueError('One complete closed database archive required')
        states = [s.split(':', 1)[1].strip() for s in receipt['clean_shutdown_control'].splitlines()
                  if s.startswith('Database cluster state:')]
        if states != ['shut down']:
            raise ValueError('Clean shutdown checkpoint required')
        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
        output = extract_verified(receipt_path.parent / 'base.tar', destination,
                                  receipt['archives'][0], progress=progress,
                                  budget_seconds=budget_seconds)
        if ((destination / 'PG_VERSION').read_text().strip() != '11'
                or not (destination / 'global/pg_control').is_file()
                or (destination / 'postmaster.pid').exists()
                or (destination / 'backup_label').exists()):
            raise ValueError('Closed PG11 checkpoint metadata invalid')
        return {'archives': [output], 'recovery_still_required': False,
                'checkpoint_sha256': hashlib.sha256(receipt_path.read_bytes()).hexdigest()}
    if (receipt.get('version') != 'map28-native-pg11-resumable-checkpoint-v1'
            or receipt.get('native_backup_exit_code') != 0):
        raise ValueError('Completed native physical backup receipt required')
    archives = {x['file']: x for x in receipt['archives']}
    if len(receipt['archives']) != 2 or set(archives) != {'base.tar', 'pg_wal.tar'}:
        raise ValueError('Expected one base archive and one WAL archive')
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    output = []
    for name, target in [('base.tar', destination), ('pg_wal.tar', destination / 'pg_wal')]:
        output.append(extract_verified(receipt_path.parent / 'native-backup' / name,
                                       target, archives[name], progress=progress,
                                       budget_seconds=max(0, budget_seconds - (time.monotonic() - started))))
    if ((destination / 'PG_VERSION').read_text().strip() != '11'
            or not (destination / 'backup_label').is_file()
            or not (destination / 'global/pg_control').is_file()
            or (destination / 'postmaster.pid').exists()):
        raise ValueError('PG11 native recovery metadata invalid')
    hba = Path(receipt['restore_original_hba_file']).read_bytes()
    if hashlib.sha256(hba).hexdigest() != receipt['restore_original_hba_sha256']:
        raise ValueError('Original authentication configuration changed')
    (destination / 'pg_hba.conf').write_bytes(hba)
    return {'checkpoint_sha256': hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            'archives': output, 'recovery_still_required': True}
