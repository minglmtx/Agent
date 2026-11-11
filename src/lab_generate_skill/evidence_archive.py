"""Standard tar.gz evidence with parallel compression and streamed file hashes.

The caller must stop all evidence writers first. This module retains every raw
member, verifies decompressed bytes, and checks source bytes again before return.
No references, hardlinks, alternate JSON schema or consumer changes are needed.
"""
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import time


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def _identity(path):
    s = path.lstat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode


def _safe(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name or str(p) != name:
        raise ValueError('Unsafe evidence path')


class _HashReader:
    def __init__(self, handle):
        self.handle = handle
        self.digest = hashlib.sha256()
        self.bytes = 0

    def read(self, size=-1):
        value = self.handle.read(size)
        self.digest.update(value); self.bytes += len(value)
        return value


def create_archive(source, destination, *, workers=1):
    """Create a new standard archive. Failed/changed input leaves no archive."""
    source, destination = Path(source), Path(destination)
    if not source.is_dir() or source.is_symlink():
        raise ValueError('Regular source directory required')
    if destination.resolve().is_relative_to(source.resolve()):
        raise ValueError('Archive must be outside evidence tree')
    if type(workers) is not int or not 1 <= workers <= 32:
        raise ValueError('Bounded compression workers required')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    files = sorted(p for p in source.rglob('*') if not p.is_dir() or p.is_symlink())
    names = {p.relative_to(source).as_posix() for p in files}
    rows = {}; started = time.monotonic(); compressor = None
    pigz = shutil.which('pigz') if workers > 1 else None
    owned = False
    try:
        with destination.open('xb') as output:
            owned = True; destination.chmod(0o600)
            if pigz:
                compressor = subprocess.Popen([pigz, '-1', '-p', str(workers), '-c'],
                    stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL)
                archive = tarfile.open(fileobj=compressor.stdin, mode='w|')
            else:
                archive = tarfile.open(fileobj=output, mode='w:gz', compresslevel=1)
            try:
                with archive:
                    for path in files:
                        name = path.relative_to(source).as_posix(); _safe(name)
                        before = _identity(path)
                        archive.inodes.clear()  # independent regular members, never tar hardlinks
                        info = archive.gettarinfo(str(path), arcname=name)
                        if info.issym():
                            rows[name] = {'type': 'symlink', 'link_target': info.linkname}
                            archive.addfile(info)
                        elif info.isfile():
                            with path.open('rb') as handle:
                                reader = _HashReader(handle); archive.addfile(info, reader)
                            if reader.bytes != info.size:
                                raise ValueError('Incomplete source member')
                            rows[name] = {'bytes': reader.bytes, 'sha256': reader.digest.hexdigest()}
                        else:
                            raise ValueError('Special evidence members are forbidden')
                        if _identity(path) != before:
                            raise ValueError('Source changed while archiving')
                if compressor:
                    compressor.stdin.close()
                    if compressor.wait(timeout=300):
                        raise RuntimeError('Parallel evidence compression failed')
            finally:
                if compressor and compressor.poll() is None:
                    compressor.kill(); compressor.wait(timeout=5)
                    compressor.stdin.close()
        write_seconds = time.monotonic()-started
        verified = set()
        with destination.open('rb') as compressed:
            archive_reader = _HashReader(compressed)
            with tarfile.open(fileobj=archive_reader, mode='r|gz') as archive:
                for member in archive:
                    if member.name in verified or member.name not in rows:
                        raise ValueError('Unexpected or duplicated archive member')
                    verified.add(member.name); expected = rows[member.name]
                    if expected.get('type') == 'symlink':
                        if not member.issym() or member.linkname != expected['link_target']:
                            raise ValueError('Archived link metadata differs')
                    else:
                        if not member.isfile() or member.size != expected['bytes']:
                            raise ValueError('Archived member type/size differs')
                        reader = _HashReader(archive.extractfile(member))
                        while reader.read(1024**2):
                            pass
                        if reader.digest.hexdigest() != expected['sha256']:
                            raise ValueError('Archived member hash differs')
            while archive_reader.read(1024**2):
                pass
        if verified != names:
            raise ValueError('Archive member set incomplete')
        verification_seconds = time.monotonic()-started-write_seconds
        # Retain the independent second source read, catching equal-size edits
        # and mutations of an earlier member while later members were written.
        for name, expected in rows.items():
            path = source/name
            if expected.get('type') == 'symlink':
                if not path.is_symlink() or os.readlink(path) != expected['link_target']:
                    raise ValueError('Source link changed after archiving')
            elif path.is_symlink() or not path.is_file() or path.stat().st_size != expected['bytes'] or sha(path) != expected['sha256']:
                raise ValueError('Source bytes changed after archiving')
        current = {p.relative_to(source).as_posix() for p in source.rglob('*')
                   if not p.is_dir() or p.is_symlink()}
        if current != names:
            raise ValueError('Source member set changed after archiving')
        return rows, {'compressor': 'pigz' if pigz else 'gzip',
            'archive_sha256': archive_reader.digest.hexdigest(),
            'compression_workers': workers if pigz else 1,
            'write_seconds': write_seconds, 'verify_seconds': verification_seconds,
            'total_seconds': time.monotonic()-started,
            'source_full_reads': 2, 'original_file_bytes_preserved': True}
    except BaseException:
        if owned:
            destination.unlink(missing_ok=True)
        raise
