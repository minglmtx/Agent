"""Read complete legacy capture-gap evidence without extracting old archives."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
from .answer_protocol_repair import pinned, regular, sha

LIMIT = 64 * 1024**2
TOTAL_LIMIT = 512 * 1024**2


def read_history(directory, record, forbidden):
    directory = Path(directory)
    physical = {str(p.relative_to(directory)): p for p in directory.rglob('*') if p.is_file()}
    if any(p.is_symlink() for p in directory.rglob('*')):
        raise ValueError('Historical query evidence cannot contain symlinks')
    members = record.get('files', {})
    archive = record.get('archived_history')
    if archive is None:
        if (not members or set(physical) != set(members) or forbidden & set(physical)
                or any(n.endswith(('.tar','.tar.gz','.zip')) or 'archive' in n for n in physical)):
            raise ValueError('Complete expanded legacy evidence without reference captures required')
        raw = {}
        for name, file in physical.items():
            if file.stat().st_size > LIMIT:
                raise ValueError('Use a bounded legacy query evidence set')
            data = regular(file)
            if members[name] != {'bytes':len(data),'sha256':sha(data)}:
                raise ValueError('Historical query artifact changed')
            raw[name] = data
        return members, raw, members
    if not isinstance(archive,dict) or set(archive) != {'archive','index','receipt'}:
        raise ValueError('Explicit complete archive/index/receipt binding required')
    expected = {'archive':directory.parent/'diagnostic-data.tar.gz',
                'index':directory.parent/'diagnostic-members.json',
                'receipt':directory/'attempt-archive.json'}
    for key,path in expected.items():
        if archive[key].get('path') != str(path):
            raise ValueError('Historical archive belongs to another attempt')
    index = json.loads(pinned(archive['index']))
    receipt = json.loads(pinned(archive['receipt']))
    digest = archive['archive'].get('sha256')
    if (index.get('archival_status') != 'complete_member_archive_saved'
            or index.get('full_output_not_sampled') is not True
            or index.get('archive_sha256') != digest or receipt.get('archive_sha256') != digest
            or receipt.get('version') != 'site-actor-node-local-archive-v1'
            or receipt.get('task_id') != directory.name
            or not isinstance(index.get('members'),dict) or not index['members']
            or index.get('member_count') != len(index['members'])):
        raise ValueError('Incomplete or mismatched historical archive')
    # Hash compressed bytes during the single sequential read. No unpacked copy.
    class Reader:
        def __init__(self,file):self.file=file;self.digest=hashlib.sha256()
        def read(self,size=-1):
            data=self.file.read(size);self.digest.update(data);return data
    seen=set();raw={};total=0;prefix=directory.name+'/'
    path=expected['archive']
    if path.is_symlink() or not path.is_file():raise ValueError('Regular historical archive required')
    with path.open('rb')as file:
        reader=Reader(file)
        with tarfile.open(fileobj=reader,mode='r|gz')as stream:
            for member in stream:
                name=member.name;relative=PurePosixPath(name)
                if (not member.isfile() or name in seen or name not in index['members']
                        or relative.is_absolute() or '..'in relative.parts or '\\'in name
                        or relative.as_posix()!=name or member.size>LIMIT):
                    raise ValueError('Invalid historical archive member')
                total+=member.size
                if total>TOTAL_LIMIT:raise ValueError('Bounded historical archive required')
                data=stream.extractfile(member).read(member.size+1)
                if index['members'][name]!={'bytes':len(data),'sha256':sha(data)}:
                    raise ValueError('Historical archive member changed')
                seen.add(name)
                if name.startswith(prefix):raw[name[len(prefix):]]=data
        while reader.read(1024**2):pass
        if reader.digest.hexdigest()!=digest or seen!=set(index['members']):
            raise ValueError('Historical archive is incomplete or changed')
    actual={name:{'bytes':len(data),'sha256':sha(data)}for name,data in raw.items()}
    if (not actual or actual!=members or receipt.get('raw_member_count')!=len(actual)
            or any(PurePosixPath(n).name in forbidden for n in raw)
            or any(n.endswith(('.tar','.tar.gz','.zip')) or 'archive'in n for n in raw)):
        raise ValueError('Archive must prove the exact missing-reference evidence set')
    artifacts=dict(members)
    for name,file in physical.items():
        data=regular(file)
        if name=='attempt-archive.json':
            if sha(data)!=archive['receipt']['sha256']:raise ValueError('Archive receipt changed')
            artifacts[name]={'bytes':len(data),'sha256':sha(data)}
        elif name not in raw or data!=raw[name]:
            raise ValueError('Retained expanded file differs from its complete archive')
    return members,raw,artifacts
