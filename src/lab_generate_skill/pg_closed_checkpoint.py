"""One-pass archival of an already cleanly stopped PG11 database."""
import hashlib
import json
import os
from pathlib import Path
import tarfile
import time


class DigestWriter:
    def __init__(self, stream, progress=None, budget_seconds=3600):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.count = 0
        self.started = self.last = time.monotonic()
        self.progress = progress
        self.budget_seconds = budget_seconds

    def write(self, value):
        count = self.stream.write(value)
        if count != len(value):
            raise OSError('Incomplete checkpoint write')
        self.digest.update(value)
        self.count += count
        now = time.monotonic()
        if now - self.started > self.budget_seconds:
            raise TimeoutError('Checkpoint archival exceeded its configured phase budget')
        if self.progress and now - self.last >= 30:
            self.progress(self.count, now - self.started)
            self.last = now
        return count


def save_closed(database, output, *, control_output, source_receipt, tables, progress=None,
                budget_seconds=3600, finalization_complete=False, range_prefixes=None):
    """Caller must have stopped and reaped its own postmaster first."""
    database, output = Path(database), Path(output)
    states = [s.split(':', 1)[1].strip() for s in control_output.splitlines()
              if s.startswith('Database cluster state:')]
    if (states != ['shut down'] or (database / 'postmaster.pid').exists()
            or (database / 'PG_VERSION').read_text().strip() != '11'):
        raise ValueError('Actual native clean shutdown required before archival')
    from .map_checkpoint_prefix import embedded_prefixes
    range_prefixes = [] if range_prefixes is None else range_prefixes
    embedded_prefixes(dict(version='map28-native-pg11-closed-checkpoint-v2',
                          verified_range_prefixes=range_prefixes))
    output.mkdir(parents=True, exist_ok=False)
    partial = output / 'base.tar.partial'
    started = time.monotonic()
    members = 0
    with partial.open('xb') as raw:
        writer = DigestWriter(raw, progress=progress, budget_seconds=budget_seconds)
        with tarfile.open(fileobj=writer, mode='w|', bufsize=1024 * 1024) as bundle:
            for directory, dirs, files in os.walk(database, followlinks=False):
                dirs.sort(); files.sort()
                for name in dirs + files:
                    p = Path(directory) / name
                    if p.is_symlink() or not (p.is_dir() or p.is_file()):
                        raise ValueError('Unexpected native database filesystem member')
                    bundle.add(p, arcname=p.relative_to(database).as_posix(), recursive=False)
                    members += 1
        raw.flush(); os.fsync(raw.fileno())
        row = {'file': 'base.tar', 'bytes': writer.count,
               'sha256': writer.digest.hexdigest(), 'members': members,
               'seconds': time.monotonic() - started}
    os.replace(partial, output / 'base.tar')
    receipt = {'version': 'map28-native-pg11-closed-checkpoint-v2',
               'archives': [row], 'clean_shutdown_control': control_output,
               'source_checkpoint': str(source_receipt),
               'source_checkpoint_sha256': hashlib.sha256(Path(source_receipt).read_bytes()).hexdigest(),
               'verified_current_tables': tables,
               'verified_range_prefixes': range_prefixes,
               'all_current_tables_complete': len(tables) == 8 and finalization_complete,
               'table_projections_complete': len(tables) == 8,
               'native_finalization_complete': finalization_complete,
               'native_HTTP_validation_complete': False,
               'task_admissions': 0, 'actor_attempts': 0, 'api_calls': 0}
    target = output / 'checkpoint.json'
    with target.open('x') as f:
        json.dump(receipt, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
    fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return receipt
