"""Retain full two-cold evidence once, read strict pinned archive members.

No archive is extracted. Every declared regular member is byte verified on the
first read, with complete archive and manifest hashes checked on every call.
The cached values are bytes; parsed proof objects cannot mutate later reads.
"""
from functools import lru_cache
from pathlib import Path
import hashlib,json,re,tarfile

VERSION='gitlab-grouped-issue-evidence-archive-v1'
SHA=re.compile(r'[0-9a-f]{64}')
MAX_ARCHIVE=2*1024**3
MAX_MEMBER=160*1024**2


def digest(path):
    p=Path(path)
    if not p.is_absolute()or not p.is_file()or p.is_symlink():raise ValueError('Actual regular absolute archive evidence required')
    if p.stat().st_size>MAX_ARCHIVE:raise ValueError('Bounded archive evidence required')
    h=hashlib.sha256()
    with p.open('rb')as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


@lru_cache(maxsize=2)
def _bytes(archive,archive_sha,manifest,manifest_sha,members):
    # Caller hashes again even on cache hits. Hash mismatch never reuses bytes.
    expected=json.loads(Path(manifest).read_text()).get('files')
    if not isinstance(expected,dict)or not expected:raise ValueError('Complete declared archive member manifest required')
    wanted=set(members);seen=set();selected={};total=0
    with tarfile.open(archive,'r:gz')as tar:
        for entry in tar:
            name=entry.name;p=Path(name);record=expected.get(name)
            if (not entry.isfile()or p.is_absolute()or '..'in p.parts or name in seen
                    or not isinstance(record,dict)or set(record)!={'bytes','sha256'}
                    or type(record['bytes'])is not int or record['bytes']!=entry.size
                    or not isinstance(record['sha256'],str)or not SHA.fullmatch(record['sha256'])):
                raise ValueError('Only complete unique declared regular archive members allowed')
            total+=entry.size
            if total>MAX_ARCHIVE or entry.size>MAX_MEMBER:raise ValueError('Bounded complete member coverage required')
            seen.add(name);h=hashlib.sha256();pieces=[]
            stream=tar.extractfile(entry)
            for block in iter(lambda:stream.read(1024*1024),b''):
                h.update(block)
                if name in wanted:pieces.append(block)
            if h.hexdigest()!=record['sha256']:raise ValueError('Actual complete member bytes differ')
            if name in wanted:selected[name]=b''.join(pieces)
    if seen!=set(expected)or set(selected)!=wanted:raise ValueError('Complete archived member coverage differs')
    return selected


def validate_reference(evidence):
    """Check actual complete archive/manifest bytes, even for scoped hits."""
    keys={'version','archive','archive_sha256','member_manifest','member_manifest_sha256','members'}
    if not isinstance(evidence,dict)or set(evidence)!=keys or evidence['version']!=VERSION:
        raise ValueError('Actual complete native issue evidence or exact pinned archive required')
    for pathkey,shakey in (('archive','archive_sha256'),('member_manifest','member_manifest_sha256')):
        if not isinstance(evidence[shakey],str)or not SHA.fullmatch(evidence[shakey])or digest(evidence[pathkey])!=evidence[shakey]:
            raise ValueError('Actual complete evidence archive or manifest changed')
    members=evidence['members']
    if not isinstance(members,dict)or set(members)!={'before','after','witness','native'}:
        raise ValueError('Four exact full native evidence members required')
    for key,spec in members.items():
        if (not isinstance(spec,dict)or set(spec)!={'name','unwrap_result'}or not isinstance(spec['name'],str)
                or type(spec['unwrap_result'])is not bool or spec['unwrap_result']is not(key=='native')):
            raise ValueError('Actual native result wrapper and complete member identity required')
    names=tuple(sorted(spec['name']for spec in members.values()))
    if len(set(names))!=4:raise ValueError('Four independently named evidence members required')
    return names


def load(evidence):
    if isinstance(evidence,dict)and set(evidence)=={'before','after','witness','native'}:
        return evidence
    names=validate_reference(evidence)
    members=evidence['members']
    raw=_bytes(evidence['archive'],evidence['archive_sha256'],evidence['member_manifest'],evidence['member_manifest_sha256'],names)
    result={}
    for key,spec in members.items():
        value=json.loads(raw[spec['name']])
        result[key]=value['result']if spec['unwrap_result']else value
    return result
