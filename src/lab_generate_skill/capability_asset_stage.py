"""Stage pinned small capability resources on local scratch, not shared inodes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

MAX_FILES = 4096
MAX_BYTES = 512 * 1024 * 1024


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): digest.update(chunk)
    return digest.hexdigest()


def _name(name):
    if not isinstance(name, str): raise ValueError('Relative asset name required')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or str(path) != name or name in ('', '.') or '\\' in name:
        raise ValueError('Unsafe capability asset name')
    return name


def stage_assets(spec, destination):
    """Verify every declared file and archive member before exposing a manifest.

    Paths in the returned manifest may point at this private extraction only
    through explicit directory bindings. No task or evaluation field is patched.
    """
    manifest_path = Path(spec['manifest'])
    if _sha(manifest_path) != spec['manifest_sha256']: raise ValueError('Capability manifest changed')
    manifest = json.loads(manifest_path.read_text())
    source_root = Path(spec['root']).resolve()
    destination = Path(destination); destination.mkdir(exist_ok=False)
    members = {}; total = 0; metadata = []

    def write(name, raw, expected):
        nonlocal total
        name = _name(name)
        if name in members: raise ValueError('Duplicate staged asset member')
        actual = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        if actual != expected: raise ValueError('Capability member bytes changed: ' + name)
        total += len(raw)
        if len(members) + len(metadata) >= MAX_FILES or total > MAX_BYTES: raise ValueError('Small capability resource budget exceeded')
        target = destination / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw); members[name] = actual

    for row in spec.get('source_files', []):
        name = _name(row['member']); path = source_root / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source_root):
            raise ValueError('Regular source asset within declared root required')
        if path.stat().st_size > MAX_BYTES: raise ValueError('Small capability source limit exceeded')
        write(name, path.read_bytes(), {k: row[k] for k in ('bytes', 'sha256')})

    for archive_spec in spec.get('archives', []):
        index_path = Path(archive_spec['index']); archive_path = Path(archive_spec['archive'])
        if _sha(index_path) != archive_spec['index_sha256']: raise ValueError('Capability archive index changed')
        index = json.loads(index_path.read_text())
        if (index.get('version') != 'complete-streaming-native-build-stage-v1'
                or index.get('member_count') != len(index.get('members', {}))
                or archive_path.stat().st_size != index['archive_bytes']
                or index['archive_bytes'] > MAX_BYTES
                or _sha(archive_path) != index['archive_sha256']):
            raise ValueError('Complete pinned small capability archive required')
        metadata_names = archive_spec.get('metadata_only_members', [])
        if (not isinstance(metadata_names, list) or any(not isinstance(v, str) for v in metadata_names)
                or len(set(metadata_names)) != len(metadata_names)
                or any(_name(v) not in index['members'] for v in metadata_names)):
            raise ValueError('Exact indexed archival metadata members required')
        seen = set()
        with tarfile.open(archive_path) as archive:
            for item in archive:
                if not item.isfile() or item.size > MAX_BYTES: raise ValueError('Only bounded regular asset files accepted')
                name = _name(item.name)
                if name not in index['members'] or name in seen: raise ValueError('Unexpected capability archive member')
                raw = archive.extractfile(item).read()
                if name in metadata_names:
                    actual = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                    if actual != index['members'][name]: raise ValueError('Archival metadata bytes changed')
                    total += len(raw)
                    if len(members) + len(metadata) >= MAX_FILES or total > MAX_BYTES:
                        raise ValueError('Small capability resource budget exceeded')
                    metadata.append({'archive_index_sha256': archive_spec['index_sha256'],
                                     'member': name, **actual})
                else:
                    write(name, raw, index['members'][name])
                seen.add(name)
        if seen != set(index['members']): raise ValueError('Capability archive is incomplete')

    resolved = deepcopy(manifest)
    for binding in spec.get('directory_bindings', []):
        route = binding['field']
        # A transport substitution may alter only the explicit preset path.
        if route != ['assets', 'native_editor_presets', 'runtime_profile', 'presets_directory']:
            raise ValueError('Only resource directory transport may be rebound')
        directory = _name(binding['directory'])
        node = resolved
        for part in route[:-1]: node = node[part]
        if (node[route[-1]] != str(source_root / directory)
                or not (destination / directory).is_dir()
                or not any(name.startswith(directory + '/') for name in members)):
            raise ValueError('Directory binding differs from the declared source assets')
        node[route[-1]] = str((destination / directory).resolve())
    output = destination.parent / 'resolved-capability-assets.json'
    if output.exists(): raise ValueError('Resolved manifest destination already exists')
    output.write_text(json.dumps(resolved, indent=2) + '\n')
    receipt = {'original_manifest_sha256': spec['manifest_sha256'],
               'resolved_manifest_sha256': _sha(output), 'staged_files': len(members),
               'verified_bytes': total, 'staged_bytes': sum(v['bytes'] for v in members.values()),
               'verified_archival_metadata': metadata, 'shared_unpacked_files_created': 0,
               'task_admissions': 0, 'api_calls': 0}
    return output, destination, receipt
