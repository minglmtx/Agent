"""Seal one actual client workspace; restore complete bytes only in TMP.

This is a storage representation, not an admission proof. All native guards
and artifact predicates are re-run against its actual restored content.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile


def pin(path):
    body = Path(path).read_bytes()
    return {'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}


def inventory(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir(): raise ValueError('Actual private client root required')
    rows = {}
    for path in sorted(root.rglob('*')):
        name = str(path.relative_to(root))
        if path.is_symlink():
            if '.git' in path.relative_to(root).parts:
                raise ValueError('Repository metadata cannot use symlink aliases')
            rows[name]={'kind':'symlink','target':os.readlink(path)}
        elif path.is_dir(): rows[name]={'kind':'directory'}
        elif path.is_file(): rows[name]={'kind':'file',**pin(path)}
        else: raise ValueError('Client artifacts cannot contain device/socket members')
    return rows


def seal(root, archive):
    root,archive=Path(root),Path(archive)
    rows=inventory(root)
    with archive.open('xb')as stream:
        with tarfile.open(fileobj=stream,mode='w:gz',compresslevel=3)as tar:
            for name in rows: tar.add(root/name,arcname=name,recursive=False)
        stream.flush();os.fsync(stream.fileno())
    os.chmod(archive,0o600)
    seen={}
    with tarfile.open(archive)as tar:
        for member in tar:
            if member.name in seen: raise ValueError('Duplicate client archive member')
            if member.isfile():
                body=tar.extractfile(member).read()
                seen[member.name]={'kind':'file','bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
            elif member.isdir():seen[member.name]={'kind':'directory'}
            elif member.issym():seen[member.name]={'kind':'symlink','target':member.linkname}
            else:raise ValueError('Unexpected client archive member type')
    if seen!=rows:raise ValueError('Actual complete client archive readback differs')
    result={'version':'sealed-actual-native-client-workspace-v1','archive':pin(archive),'members':rows,
        'actual_complete_client_bytes_verified':True,'namespace_retired_after_seal':True}
    # Only the exact newly-created attempt namespace is retired. The complete
    # actual archive remains available for original native/artifact predicates.
    shutil.rmtree(root)
    return result


def restore(archive, receipt, root):
    archive,root=Path(archive),Path(root)
    if receipt.get('version')!='sealed-actual-native-client-workspace-v1' or pin(archive)!=receipt.get('archive'):
        raise ValueError('Original actual client workspace archive pin required')
    if root.exists():raise ValueError('Restore requires a fresh TMP directory')
    root.mkdir(mode=0o700,parents=True)
    expected=receipt['members']; seen={}
    with tarfile.open(archive)as tar:
        members=list(tar)
        for member in members:
            path=Path(member.name)
            if path.is_absolute()or '..'in path.parts or not path.parts or member.name in seen:
                raise ValueError('Unsafe or duplicate client workspace member')
            if any(expected.get(str(parent),{}).get('kind')=='symlink'for parent in path.parents if str(parent)!='.'):
                raise ValueError('Client member cannot descend through an archived symlink')
            destination=root/path
            if member.isfile():
                body=tar.extractfile(member).read();actual={'kind':'file','bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
                if actual!=expected.get(member.name):raise ValueError('Client artifact bytes changed')
                destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True);destination.write_bytes(body);os.chmod(destination,member.mode&0o777)
            elif member.isdir():
                actual={'kind':'directory'};destination.mkdir(mode=0o700,parents=True,exist_ok=True)
            elif member.issym():
                actual={'kind':'symlink','target':member.linkname}
                if '.git'in path.parts:raise ValueError('Client repository metadata symlink refused')
                destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True);destination.symlink_to(member.linkname)
            else:raise ValueError('Unsupported client artifact member')
            if actual!=expected.get(member.name):raise ValueError('Client archive metadata changed')
            seen[member.name]=actual
    if seen!=expected:raise ValueError('Client workspace member coverage incomplete')
    return root
