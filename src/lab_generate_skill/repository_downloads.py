"""Compare native downloaded ZIP contents without extracting untrusted paths.

ZIP metadata, ordering, timestamps and the generated enclosing folder may differ.
Relative member paths and bytes must match the independent Git archive exactly.
This helper alone grants neither task admission nor reward.
"""
import hashlib
import io
from pathlib import PurePosixPath
import zipfile


def zip_manifest(payload, *, max_bytes=512 * 1024 * 1024, max_entries=20000):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = archive.infolist()
        if len(entries) > max_entries or sum(i.file_size for i in entries) > max_bytes:
            raise ValueError('Archive exceeds inspection budget')
        seen = set(); roots = set(); rows = {}
        for entry in entries:
            name = entry.filename
            parts = name.rstrip('/').split('/')
            if (not name or name.startswith('/') or '\\' in name or
                    any(p in ('', '.', '..') for p in parts) or entry.flag_bits & 1):
                raise ValueError('Unsafe or encrypted archive member')
            if name in seen:
                raise ValueError('Duplicate archive member')
            seen.add(name); roots.add(parts[0])
            if entry.is_dir():
                continue
            if len(parts) < 2:
                raise ValueError('Expected one enclosing archive directory')
            relative = str(PurePosixPath(*parts[1:]))
            digest = hashlib.sha256(); size = 0
            with archive.open(entry) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    size += len(chunk)
                    if size > entry.file_size:
                        raise ValueError('Archive member length mismatch')
                    digest.update(chunk)
            if size != entry.file_size:
                raise ValueError('Archive member length mismatch')
            rows[relative] = {'bytes': size, 'sha256': digest.hexdigest()}
        if len(roots) != 1 or not rows:
            raise ValueError('Missing or ambiguous archive root')
        return dict(sorted(rows.items()))


def compare_zip(payload, reference):
    actual = zip_manifest(payload)
    missing = sorted(reference.keys() - actual.keys())
    extra = sorted(actual.keys() - reference.keys())
    changed = sorted(k for k in actual.keys() & reference.keys() if actual[k] != reference[k])
    return {'matches': not (missing or extra or changed), 'files': len(actual),
            'missing': missing, 'extra': extra, 'changed': changed}
