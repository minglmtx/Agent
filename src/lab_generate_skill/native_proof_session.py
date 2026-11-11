"""Reuse one fully checked proof inside its private, live bootstrap context.

This never accepts a persisted success flag as proof. The full native validator
runs before the first entry is retained. Subsequent calls check the same source,
contract, descriptor, validator and private file identities. Parsed proof JSON
is immutable; explicit deep copies remain ordinary independent JSON objects.
There is no cross-process cache and no reuse of live website state.
"""
from copy import deepcopy
from pathlib import Path
import stat
import hashlib


def _readonly(*args, **kwargs):
    raise TypeError('Verified proof JSON is read-only; make an explicit copy')


class _Dict(dict):
    __init__ = _readonly
    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _readonly

    def __deepcopy__(self, memo):
        return {deepcopy(k, memo): deepcopy(v, memo) for k, v in self.items()}


class _List(list):
    __init__ = _readonly
    __setitem__ = __delitem__ = append = extend = insert = pop = remove = clear = reverse = sort = __iadd__ = __imul__ = _readonly

    def __deepcopy__(self, memo):
        return [deepcopy(v, memo) for v in self]


def _freeze(value, memo):
    if isinstance(value, (_Dict, _List)):
        return value
    if not isinstance(value, (dict, list)):
        return value
    ident = id(value)
    if ident in memo:
        return memo[ident]
    target = dict.__new__(_Dict) if isinstance(value, dict) else list.__new__(_List)
    memo[ident] = target
    if isinstance(value, dict):
        for k, v in value.items():
            dict.__setitem__(target, k, _freeze(v, memo))
    else:
        for v in value:
            list.append(target, _freeze(v, memo))
    return target


def _files(directories,extra_files=()):
    """Local POSIX change guard after byte verification by the original gate.

    ctime is included: restoring mtime after an edit must not preserve the guard.
    Some filesystems have coarse change timestamps. Exact byte digests also detect
    same-size edits followed by restored mtime. This check runs at proof reuse,
    not at every browser observation. No links or special files are permitted.
    """
    found = {}
    for directory in directories:
        root = Path(directory)
        if root.is_symlink() or not root.is_dir():
            raise ValueError('Private native proof directory is unavailable')
        for p in [root, *root.rglob('*')]:
            s = p.lstat()
            if not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)):
                raise ValueError('Native proof contains a link or special file')
            digest=None
            if stat.S_ISREG(s.st_mode):
                h=hashlib.sha256()
                with p.open('rb')as stream:
                    for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
                after=p.lstat()
                if (after.st_dev,after.st_ino,after.st_mode,after.st_size,after.st_mtime_ns,after.st_ctime_ns)!=(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns):
                    raise ValueError('Native proof changed during byte verification')
                digest=h.hexdigest()
            found[str(p.absolute())] = (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns,digest)
    for path in extra_files:
        p=Path(path);s=p.lstat()
        if not stat.S_ISREG(s.st_mode):raise ValueError('Regular native proof guard file required')
        h=hashlib.sha256()
        with p.open('rb')as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
        found[str(p.absolute())]=(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns,h.hexdigest())
    if not found:
        raise ValueError('Original on-disk proof is required')
    return found


def _proof_key(source):
    if source.get('version') in ('native-csv-retained-controls-reset-supplement-v1',
                                    'native-template-retained-controls-supplement-v1'):
        return 'groups'
    return 'cycles'


def _validator(source):
    driver = source['driver']
    callback = driver.require_supplement if _proof_key(source) == 'groups' else driver.require_two_cold
    return (getattr(callback, '__self__', None), getattr(callback, '__func__', callback))


class NativeProofSession:
    """At most one retained task proof; close when its bootstrap exits."""
    def __init__(self):
        self._closed = False
        self._entry = None
        self.full_verifications = 0
        self.reuses = 0

    def close(self):
        self._closed = True
        self._entry = None

    def __enter__(self):
        if self._closed:
            raise ValueError('Native proof session expired')
        return self

    def __exit__(self, *args):
        self.close()

    def reuse_verified(self, contract, proof):
        """Recheck a previously issued immutable proof; never create admission.

        Native hooks can consume the adapter's real proof without rerunning the
        whole cold predicate. Identity, callback and all raw-file change guards
        still run through verify(); an equivalent dictionary is not a token.
        """
        entry = self._entry
        if self._closed or entry is None or proof is not entry['frozen']:
            raise ValueError('An active proof issued by this native session is required')
        def no_new_verification():
            raise ValueError('Cached proof reuse cannot grant new admission')
        return self.verify(contract, entry['descriptor'], entry['source'], no_new_verification)

    def verify(self, contract, descriptor, source, validate):
        if self._closed:
            raise ValueError('Native proof session expired')
        entry = self._entry
        if entry is not None and entry['source'] is source:
            frozen = entry['frozen']
            if (contract != entry['contract'] or descriptor != entry['descriptor']
                    or _proof_key(source) != entry['proof_key']
                    or source['contract'] != frozen['contract']
                    or source['gate_return'] != frozen['gate_return']
                    or source.get(entry['proof_key']) is not frozen[entry['proof_key']]
                    or source['driver'] is not frozen['driver']
                    or _validator(source) != entry['validator']
                    or source['directories'] != frozen['directories']
                    or source.get('native_packet') != frozen.get('native_packet')
                    or _files(source['directories'],source.get('guard_files',())) != entry['files']):
                self._entry = None
                raise ValueError('Previously verified native proof changed')
            self.reuses += 1
            return frozen
        # Never retain many huge per-task snapshots in a multi-task worker.
        self._entry = None
        validate()
        self.full_verifications += 1
        frozen = _freeze(source, {})
        # The live resolver subsequently returns this exact immutable proof,
        # rather than keeping an independently mutable copy of the same cycles.
        key = _proof_key(source)
        source[key] = frozen[key]
        self._entry = dict(source=source, frozen=frozen, contract=deepcopy(contract),
                           descriptor=deepcopy(descriptor), validator=_validator(source), proof_key=key,
                           files=_files(source['directories'],source.get('guard_files',())))
        return frozen
