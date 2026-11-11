"""Load pinned original proofs without expanding them on shared storage.

This is a storage adapter, never an admission validator. The caller must run
the same full gate on the returned proof. An archive is expanded once into a
private temporary directory; only one parsed proof is retained at a time.
"""
import atexit
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tarfile
import tempfile

from .native_proof_session import _freeze
from .source_revision_binding import fingerprint

VERSION = 'archived-original-admission-proof-v1'


def file_identity(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Original proof must be a regular file')
    s=path.stat()
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def file_sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(4*1024**2),b''):h.update(b)
    return h.hexdigest()


class ArchivedProofStore:
    def __init__(self, *, directory=None):
        self.directory=directory
        self.temp=None
        self.archives={}
        self.parsed=None
        self.closed=False

    def close(self):
        self.parsed=None
        self.archives.clear()
        if self.temp is not None:self.temp.cleanup()
        self.closed=True

    def __enter__(self):return self
    def __exit__(self,*args):self.close()

    def resolve(self,contract,descriptor):
        if self.closed:raise ValueError('Original proof store has expired')
        required={'storage_format','source_task_id','contract_fingerprint','archive',
                  'archive_sha256','member','member_sha256','member_bytes'}
        if (not isinstance(descriptor,dict) or set(descriptor)!=required
                or descriptor['storage_format']!=VERSION
                or descriptor['source_task_id']!=contract.get('source_task_id')
                or descriptor['contract_fingerprint']!=fingerprint(contract)):
            raise ValueError('Exact source-bound original proof descriptor required')
        for k in ('archive_sha256','member_sha256'):
            v=descriptor[k]
            if not isinstance(v,str) or len(v)!=64 or any(x not in '0123456789abcdef' for x in v):
                raise ValueError('Pinned SHA256 required')
        name=descriptor['member'];member=PurePosixPath(name)
        if (member.is_absolute() or '..' in member.parts or str(member)!=name
                or member.name!='normal-admission-proof.json'
                or member.parent.name!=contract['source_task_id']
                or type(descriptor['member_bytes']) is not int or descriptor['member_bytes']<=0):
            raise ValueError('Exact source proof member required')
        archive=Path(descriptor['archive'])
        if not archive.is_absolute():raise ValueError('Absolute original archive required')
        identity=file_identity(archive);key=str(archive)
        cached=self.archives.get(key)
        if cached is not None:
            if identity!=cached['identity'] or descriptor['archive_sha256']!=cached['sha256']:
                raise ValueError('Original archive changed after verification')
        else:
            if file_sha(archive)!=descriptor['archive_sha256']:
                raise ValueError('Original archive hash differs')
            if self.temp is None:
                self.temp=tempfile.TemporaryDirectory(prefix='original-proofs-',dir=self.directory)
            root=Path(self.temp.name)/descriptor['archive_sha256'];root.mkdir(mode=0o700)
            entries={};seen=set()
            # Extract only proof objects, not old screenshots/step directories.
            with tarfile.open(archive,'r|gz') as tar:
                for m in tar:
                    p=PurePosixPath(m.name)
                    if m.name in seen or p.is_absolute() or '..' in p.parts:
                        raise ValueError('Unsafe or duplicate archive member')
                    seen.add(m.name)
                    if p.name!='normal-admission-proof.json':continue
                    if not m.isfile():raise ValueError('Proof member is not a file')
                    dest=root/hashlib.sha256(m.name.encode()).hexdigest()
                    h=hashlib.sha256();size=0
                    with dest.open('xb') as out:
                        dest.chmod(0o600)
                        stream=tar.extractfile(m)
                        for b in iter(lambda:stream.read(4*1024**2),b''):
                            out.write(b);h.update(b);size+=len(b)
                    entries[m.name]={'path':dest,'sha256':h.hexdigest(),'bytes':size,
                                     'identity':file_identity(dest)}
            if file_identity(archive)!=identity:raise ValueError('Archive changed during extraction')
            cached={'identity':identity,'sha256':descriptor['archive_sha256'],'entries':entries}
            self.archives[key]=cached
        row=cached['entries'].get(name)
        if (row is None or row['sha256']!=descriptor['member_sha256']
                or row['bytes']!=descriptor['member_bytes']
                or file_identity(row['path'])!=row['identity']):
            raise ValueError('Pinned original proof bytes differ')
        parse_key=(key,name,row['sha256'])
        if self.parsed is None or self.parsed[0]!=parse_key:
            self.parsed=None
            with row['path'].open() as f:value=json.load(f)
            if not isinstance(value,dict):raise ValueError('Complete original proof object required')
            self.parsed=(parse_key,_freeze(value,{}))
        return self.parsed[1]


_store=None


def resolve(contract,proof):
    if not isinstance(proof,dict) or proof.get('storage_format')!=VERSION:return proof
    global _store
    if _store is None:
        # Only shared-storage read-only admission preparation may run outside
        # Slurm; compute jobs use their private node-local TMPDIR.
        _store=ArchivedProofStore(directory=os.environ.get('TMPDIR'))
        atexit.register(_store.close)
    return _store.resolve(contract,proof)
