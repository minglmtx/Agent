"""Read byte-pinned original references after temporary producer paths expire.

No extraction or receipt rewriting. The caller's validated proof supplies the
archive pins; this transport layer cannot itself grant task admission.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path, PurePosixPath
import hashlib
import io
import json
import tarfile

_sources = ContextVar('original_reference_sources', default=())


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('Unsafe original archive member')
    return str(path)


def member(raw, name):
    name = safe(name)
    with tarfile.open(fileobj=io.BytesIO(raw)) as stream:
        matches = [m for m in stream if m.name == name]
        if len(matches) != 1 or not matches[0].isfile():
            raise ValueError('Missing, duplicate or non-regular original member')
        return stream.extractfile(matches[0]).read()


@lru_cache(maxsize=8)
def _load(path, expected, signature):
    raw = Path(path).read_bytes()
    stat = Path(path).stat()
    if (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) != signature or digest(raw) != expected:
        raise ValueError('Original archive bytes changed')
    return raw


def archive_bytes(pin):
    path = Path(pin['path'])
    if path.is_symlink() or not path.is_file():
        raise ValueError('Regular pinned original archive required')
    stat = path.stat()
    return _load(str(path), pin['sha256'],
                 (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))


@contextmanager
def reference_sources(proof):
    token = _sources.set((proof,) + _sources.get())
    try:
        yield
    finally:
        _sources.reset(token)


def read_bytes(locator, proof):
    path = Path(locator['file'])
    if path.exists():
        raw = path.read_bytes()
    else:
        raw = None
        for source in (proof,) + _sources.get():
            refs = source.get('original_archive_refs', [])
            suppliers = source.get('durable_original_byte_suppliers', [])
            roots = source.get('original_producer_output_directories', [])
            if not refs and not suppliers and not roots:
                continue
            if len(refs) != len(suppliers) or len(refs) != len(roots):
                raise ValueError('Incomplete original reference archive bindings')
            for ref, supplier, root in zip(refs, suppliers, roots):
                try:
                    path.relative_to(root)
                except ValueError:
                    continue
                def outer_name(old):
                    return safe(str(PurePosixPath(ref['member_prefix']) /
                                    PurePosixPath(old).relative_to(root)))
                outer = archive_bytes(ref['archive'])
                mapping_raw = member(outer, outer_name(supplier['member_map_file']))
                if digest(mapping_raw) != supplier['member_map_sha256']:
                    raise ValueError('Original member map changed')
                mapping = json.loads(mapping_raw)
                if (mapping.get('version') != 'map-source-original-byte-archive-v1'
                        or mapping.get('archive') != supplier['archive_file']
                        or mapping.get('archive_sha256') != supplier['archive_sha256']):
                    raise ValueError('Original member map/archive mismatch')
                matches = [r for r in mapping['members'] if r['original_producer_path'] == str(path)]
                if len(matches) != 1:
                    raise ValueError('Exact original producer path missing or duplicated')
                row = matches[0]
                if row.get('raw_receipt_rewritten') is not False or any(row[k] != locator[k] for k in ('bytes', 'sha256')):
                    raise ValueError('Original byte locator changed')
                inner = member(outer, outer_name(supplier['archive_file']))
                if digest(inner) != supplier['archive_sha256']:
                    raise ValueError('Original source archive changed')
                raw = member(inner, row['original_archive_member_suffix'])
                break
            if raw is not None:
                break
        if raw is None:
            raise ValueError('Pinned original reference bytes unavailable')
    if len(raw) != locator['bytes'] or digest(raw) != locator['sha256']:
        raise ValueError('Original reference content changed')
    return raw
