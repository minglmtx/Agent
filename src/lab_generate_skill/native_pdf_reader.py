"""Load the byte-pinned PDF parser once per worker, from local immutable data.

Only explicit PDF/print capabilities request this dependency. Package members
are extracted to an owned temporary directory; no installation, network access
or fallback to a different parser is performed.
"""
import atexit
import hashlib
import importlib
import json
from pathlib import Path, PurePosixPath
import platform
import sys
import tarfile
import tempfile
import threading

VERSION = 'pinned-native-pdf-reader-v1'
MANIFEST = 'configs/native-pdf-reader.json'
MAX_PACKED = 96 * 1024**2
MAX_UNPACKED = 128 * 1024**2
_lock = threading.Lock()
_loaded = {}


def required(contract):
    """Capability selection is independent of task identity and expected answer."""
    native = contract.get('public_completion', {}).get('original_contract')
    native = native if isinstance(native, dict) else contract
    return (contract.get('browser_capabilities', {}).get('print_to_pdf') is True
            or native.get('browser_capabilities', {}).get('print_to_pdf') is True
            or native.get('candidate_completion', {}).get('family') == 'pdf_artifact')


def _identity(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Regular pinned PDF package file required: ' + str(path))
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _close():
    for cached in _loaded.values():
        cached['temporary'].cleanup()
    _loaded.clear()


atexit.register(_close)


def load(project):
    """Verify the configured ABI, full archive and every imported package byte."""
    manifest = Path(project).resolve() / MANIFEST
    before = _identity(manifest)
    raw = manifest.read_bytes()
    if _identity(manifest) != before:
        raise ValueError('PDF dependency manifest changed during read')
    config = json.loads(raw)
    if (config.get('version') != VERSION or config.get('module') != 'pymupdf'
            or config.get('module_version') != '1.26.5'
            or config.get('runtime_network_required') is not False
            or config.get('python_cache_tag') != sys.implementation.cache_tag
            or config.get('machine') != platform.machine()):
        raise ValueError('Pinned PDF reader configuration or native ABI differs')
    reference = config['archive']
    archive = Path(reference['path'])
    if not archive.is_absolute():
        raise ValueError('Absolute pinned PDF package archive required')
    archive_identity = _identity(archive)
    if not 0 < archive_identity[2] == reference['bytes'] <= MAX_PACKED:
        raise ValueError('PDF package archive exceeds its declared bound')
    members = config['members']
    if (not isinstance(members, dict) or not 0 < len(members) <= 128
            or not 0 < sum(r['bytes'] for r in members.values()) <= MAX_UNPACKED
            or not {'pymupdf/__init__.py', 'pymupdf/mupdf.py', 'pymupdf/_mupdf.so',
                    'pymupdf/extra.py', 'pymupdf/_extra.so'} <= members.keys()):
        raise ValueError('Complete bounded PDF runtime package required')
    key = _sha(raw), str(archive), archive_identity
    with _lock:
        if key in _loaded:
            cached = _loaded[key]
            if any(_identity(path) != identity for path, identity in cached['files'].items()):
                raise ValueError('Loaded PDF dependency bytes changed')
            module = importlib.import_module('pymupdf')
            if (not Path(module.__file__).resolve().is_relative_to(cached['root'])
                    or module.VersionBind != config['module_version']):
                raise ValueError('Loaded PDF module no longer belongs to this worker')
            return dict(cached['report'], verified_clean_reuse=True)
        if 'pymupdf' in sys.modules:
            raise ValueError('PDF parser was imported before its pinned capability preflight')
        # Reading the original archive and checking all member hashes happens
        # once. Later tasks reuse this process-owned, identity-checked package.
        packed = archive.read_bytes()
        if (_identity(archive) != archive_identity
                or len(packed) != reference['bytes'] or _sha(packed) != reference['sha256']):
            raise ValueError('PDF package archive bytes changed')
        import io
        temporary = tempfile.TemporaryDirectory(prefix='lab-pdf-reader-')
        root = Path(temporary.name)
        seen, files = set(), {}
        inserted = False
        try:
            with tarfile.open(fileobj=io.BytesIO(packed), mode='r:gz') as stream:
                for member in stream:
                    name = member.name
                    parts = PurePosixPath(name).parts
                    if (not member.isfile() or name not in members or name in seen
                            or not parts or parts[0] != 'pymupdf'
                            or PurePosixPath(name).is_absolute() or '..' in parts
                            or '__pycache__' in parts or not 0 <= member.size <= MAX_UNPACKED):
                        raise ValueError('Unsafe or unpinned PDF package member')
                    expected = members[name]
                    data = stream.extractfile(member).read()
                    if (member.size != expected['bytes'] or len(data) != expected['bytes']
                            or _sha(data) != expected['sha256']):
                        raise ValueError('PDF package member bytes changed: ' + name)
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    files[target] = _identity(target)
                    seen.add(name)
            if seen != set(members):
                raise ValueError('PDF runtime package is incomplete')
            sys.path.insert(0, str(root))
            inserted = True
            module = importlib.import_module('pymupdf')
            if (not Path(module.__file__).resolve().is_relative_to(root / 'pymupdf')
                    or module.VersionBind != config['module_version']):
                raise ValueError('Imported PDF parser version or location differs')
            report = dict(version=VERSION, ready=True, module='pymupdf',
                module_version=module.VersionBind, manifest_sha256=_sha(raw),
                archive_sha256=reference['sha256'], verified_members=len(seen),
                extracted_bytes=sum(r['bytes'] for r in members.values()),
                runtime_network_required=False, installed_into_environment=False,
                materialized_in_worker_tmp=True, actor_attempts=0, api_calls=0)
            _loaded[key] = dict(temporary=temporary, root=root, files=files, report=report)
            return dict(report, verified_clean_reuse=False)
        except BaseException:
            if inserted:
                sys.path.remove(str(root))
                for name in list(sys.modules):
                    if name == 'pymupdf' or name.startswith('pymupdf.'):
                        sys.modules.pop(name, None)
            temporary.cleanup()
            raise
