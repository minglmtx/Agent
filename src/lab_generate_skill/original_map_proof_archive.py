"""Exact original byte suppliers, compressed per source; never receipt rewrites.

The member map retains producer paths and original worker-member suffixes.
Restoration is transport only and must precede the unchanged family predicates.
"""
from contextlib import contextmanager
import builtins
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

VERSION='map-source-original-byte-archive-v1'
def digest(raw):return hashlib.sha256(raw).hexdigest()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def safe(name):
    p=PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name or p.as_posix()!=name:
        raise ValueError('Unsafe exact original member: '+str(name))
    return name
def regular_files(root):
    root=Path(root)
    if root.is_symlink():raise ValueError('Symlink evidence root')
    files={}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('Symlink original evidence')
        if p.is_file():files[p.relative_to(root).as_posix()]=p
        elif not p.is_dir():raise ValueError('Nonregular original evidence')
    return files
def pack_source(source_directory,out,durable):
    source_directory,out,durable=map(Path,(source_directory,out,durable))
    durable.parent.mkdir(parents=True,exist_ok=True)
    archive=durable.with_suffix('.tar.gz');mapfile=durable.with_suffix('.members.json')
    if archive.exists() or mapfile.exists():raise ValueError('Original byte supplier is immutable')
    files=regular_files(source_directory)
    if not files:raise ValueError('Complete source evidence is empty')
    members=[]
    with tarfile.open(archive,'x:gz') as tar:
        for _,path in files.items():
            suffix=safe(path.relative_to(out).as_posix());before=sha(path)
            info=tar.gettarinfo(str(path),arcname=suffix)
            if not info.isfile():raise ValueError('Only regular source bytes can be supplied')
            with path.open('rb') as f:tar.addfile(info,f)
            if sha(path)!=before:raise ValueError('Source bytes changed during immutable capture')
            members.append({'original_producer_path':str(path),
                'original_archive_member_suffix':suffix,'bytes':info.size,'sha256':before,
                'raw_receipt_rewritten':False})
    value={'version':VERSION,'archive':str(archive),'archive_sha256':sha(archive),
        'source_task_id':source_directory.name,'members':members,
        'complete_source_directory_preserved':True,'raw_bytes_rewritten':False,
        'archive_identity_not_replaced':True,
        'excluded_derived_members':['durable-original-byte-suppliers.json']}
    mapfile.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return {'version':VERSION,'archive_file':str(archive),'archive_sha256':value['archive_sha256'],
        'member_map_file':str(mapfile),'member_map_sha256':sha(mapfile),
        'original_member_count':len(members),'raw_bytes_rewritten':False,
        'expanded_durable_copy_created':False}
def validate_map(value):
    if (value.get('version')!=VERSION or value.get('complete_source_directory_preserved') is not True
        or value.get('raw_bytes_rewritten') is not False or value.get('archive_identity_not_replaced') is not True
        or value.get('excluded_derived_members')!=['durable-original-byte-suppliers.json']):
        raise ValueError('Exact compressed original source map required')
    members=value.get('members');known={};paths=set()
    if not isinstance(members,list) or not members:raise ValueError('Complete original member list required')
    for row in members:
        name=safe(row['original_archive_member_suffix']);original=row['original_producer_path']
        if name in known or original in paths:raise ValueError('Duplicate member/original path')
        if (not Path(original).is_absolute() or row.get('raw_receipt_rewritten') is not False
            or type(row.get('bytes')) is not int or row['bytes']<0
            or len(row.get('sha256',''))!=64 or name.split('/')[0]!=value['source_task_id']):
            raise ValueError('Original source path/byte identity changed')
        paths.add(original);known[name]=row
    return known
def restore_source(supplier,destination,*,original_files=None,original_prefix=None):
    """Verify every compressed member, restore only to a new local directory.

    original_files is the COMPLETE worker archive manifest, not a projection.
    If supplied, the full source member set (except derived supplier metadata)
    and bytes must match that independently verified original worker archive.
    """
    destination=Path(destination)
    if destination.exists():raise ValueError('Never reuse a mutable restoration tree')
    mapfile=Path(supplier['member_map_file']);archive=Path(supplier['archive_file'])
    if mapfile.is_symlink() or archive.is_symlink():raise ValueError('Regular immutable suppliers required')
    if sha(mapfile)!=supplier['member_map_sha256'] or sha(archive)!=supplier['archive_sha256']:
        raise ValueError('Original source archive/map SHA differs')
    value=json.loads(mapfile.read_bytes());known=validate_map(value)
    if (str(archive)!=value['archive'] or value['archive_sha256']!=supplier['archive_sha256']
        or len(known)!=supplier['original_member_count'] or supplier.get('raw_bytes_rewritten') is not False):
        raise ValueError('Supplier/map binding differs')
    if original_files is not None:
        prefix=safe(original_prefix).rstrip('/')+'/'+value['source_task_id']+'/'
        source={n[len(original_prefix)+1:]:r for n,r in original_files.items()
            if n.startswith(prefix) and n!=prefix+'durable-original-byte-suppliers.json'}
        expected={n:{'bytes':r['bytes'],'sha256':r['sha256']} for n,r in known.items()}
        if source!=expected:raise ValueError('Supplier is not the complete original worker source subtree')
    destination.mkdir(parents=True);found=set();aliases={}
    with tarfile.open(archive,'r:gz') as tar:
        for member in tar:
            name=safe(member.name)
            if name in found or name not in known or not member.isfile():raise ValueError('Duplicate/new/nonregular supplier member')
            found.add(name);row=known[name];target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
            h=hashlib.sha256();size=0
            with tar.extractfile(member) as src,target.open('xb') as dst:
                for block in iter(lambda:src.read(1024*1024),b''):dst.write(block);h.update(block);size+=len(block)
            if size!=member.size or size!=row['bytes'] or h.hexdigest()!=row['sha256']:
                raise ValueError('Restored original bytes differ')
            aliases[row['original_producer_path']]=target
    if found!=set(known):raise ValueError('Missing original supplier member')
    return {'map':value,'aliases':aliases,'files':known,'restore_root':destination}
def restore_from_worker_archive(supplier,reference,original_output,destination):
    """Portable consumer: verify the full original worker, retain two suppliers.

    Only consumer-needed archive/map members are temporarily restored. This
    directory is not described as an expanded copy of the complete worker.
    """
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    def checked(pair):
        p=Path(pair['path'])
        if p.is_symlink() or not p.is_file() or sha(p)!=pair['sha256']:raise ValueError('Original portable worker artifact SHA differs')
        return p
    manifest=json.loads(checked(reference['member_manifest']).read_bytes())
    receipt=json.loads(checked(reference['receipt']).read_bytes())
    if (receipt.get('version')!='original-native-cold-archive-receipt-v1'
        or any(type(receipt.get(k)) is not int or receipt[k]!=0 for k in ('exit_code','actor_attempts','api_calls'))
        or receipt.get('training_admitted') is not False or receipt.get('archive_verified') is not True
        or receipt.get('archive_sha256')!=reference['archive']['sha256']
        or receipt.get('member_manifest_sha256')!=reference['member_manifest']['sha256']
        or str(Path(receipt['raw_archive']).resolve())!=str(Path(reference['archive']['path']).resolve())
        or str(Path(receipt['complete_member_manifest']).resolve())!=str(Path(reference['member_manifest']['path']).resolve())):
        raise ValueError('Original complete portable CPU receipt required')
    if manifest.get('version')!='complete-local-original-native-cpu-archive-v1':raise ValueError('Complete original portable member manifest required')
    expected=manifest['files'];prefix=safe(reference['member_prefix']);output=Path(original_output)
    if not output.is_absolute():raise ValueError('Exact original producer root required')
    wanted={prefix+'/'+safe(Path(supplier[k]).relative_to(output).as_posix()):supplier[k] for k in ('archive_file','member_map_file')}
    if any(name not in expected for name in wanted):raise ValueError('Portable original archive/map member missing')
    archive=Path(reference['archive']['path'])
    if archive.is_symlink() or not archive.is_file():raise ValueError('Original regular portable archive required')
    before=archive.stat();found={};retained={};compressed=hashlib.sha256()
    class Reader:
        def read(self,size=-1):
            raw=self.stream.read(size);compressed.update(raw);return raw
    with archive.open('rb') as raw:
        reader=Reader();reader.stream=raw
        with tarfile.open(fileobj=reader,mode='r|gz') as tar:
            for member in tar:
                name=safe(member.name)
                if name in found:raise ValueError('Duplicate complete portable original member')
                if member.issym():found[name]={'type':'symlink','link_target':member.linkname};continue
                if not member.isfile():raise ValueError('Unsupported complete portable original member')
                h=hashlib.sha256();size=0;chunks=[]
                with tar.extractfile(member) as src:
                    for block in iter(lambda:src.read(1024*1024),b''):
                        h.update(block);size+=len(block)
                        if name in wanted:chunks.append(block)
                if size!=member.size:raise ValueError('Truncated complete original member')
                found[name]={'bytes':size,'sha256':h.hexdigest()}
                if name in wanted:retained[name]=b''.join(chunks)
        while reader.read(1024*1024):pass
    after=archive.stat()
    if (compressed.hexdigest()!=reference['archive']['sha256'] or found!=expected or len(found)!=receipt['raw_member_count']
        or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=
        (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)):
        raise ValueError('Complete original portable worker archive/member bytes changed')
    portable={'restore_root':destination/'supplier-members','aliases':{},'files':{}}
    for name,original in wanted.items():
        relative=safe(name[len(prefix)+1:]);target=portable['restore_root']/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(retained[name])
        portable['aliases'][original]=target;portable['files'][relative]=dict(expected[name],original_producer_path=original)
    with original_path_suppliers([portable]):restored=restore_source(supplier,destination/'source-members',original_files=expected,original_prefix=prefix)
    restored['transport']={'complete_original_archive_verified':True,'original_worker_members_verified':len(found),
        'original_archive':reference['archive'],'original_member_manifest':reference['member_manifest'],
        'temporary_supplier_members_only':True,'temporary_directory_is_not_complete_worker_expansion':True}
    return restored
@contextmanager
def restored_composition_source(proof,temporary_root):
    """Keep exact original-path byte suppliers active for a normal private read.

    This is transport, not an admission loader or source promotion. The caller
    must verify its pinned proof and call the current family admission gate.
    """
    suppliers=proof['durable_original_byte_suppliers'];refs=proof['original_archive_refs'];outputs=proof['original_producer_output_directories']
    if len(suppliers)!=2 or len(refs)!=2 or len(outputs)!=2:raise ValueError('Two complete original cold byte suppliers required')
    restored=[restore_from_worker_archive(s,r,o,Path(temporary_root)/('cold-'+str(i))) for i,(s,r,o) in enumerate(zip(suppliers,refs,outputs))]
    with original_path_suppliers(restored):yield restored
@contextmanager
def original_path_suppliers(restored):
    """Supply exact archived bytes at their ORIGINAL reference paths in memory.

    Raw proof paths and all private fingerprint fields remain unchanged. This
    narrow process-local read adapter never writes/repins original receipts.
    Callers must keep it active throughout the normal runner's private reads.
    """
    aliases={};expected={}
    for item in restored:
        for original,target in item['aliases'].items():
            row=item['files'][target.relative_to(item['restore_root']).as_posix()]
            if original in aliases and expected[original]!=row:raise ValueError('Conflicting original path byte suppliers')
            aliases[original]=target;expected[original]=row
    old_open=Path.open;old_stat=Path.stat;old_exists=Path.exists;old_is_file=Path.is_file;old_builtin=builtins.open
    def mapped(path):
        target=aliases.get(str(path))
        if target is not None:
            row=expected[str(path)]
            with old_open(target,'rb') as f:raw=f.read()
            if len(raw)!=row['bytes'] or digest(raw)!=row['sha256']:raise ValueError('Local restored supplier changed before consumption')
        return target or path
    def path_open(path,mode='r',*a,**kw):
        if str(path) in aliases and any(x in mode for x in 'wax+'):raise ValueError('Original suppliers are read-only')
        return old_open(mapped(path),mode,*a,**kw)
    def builtin_open(path,mode='r',*a,**kw):
        if isinstance(path,(str,Path)):
            if str(path) in aliases and any(x in mode for x in 'wax+'):raise ValueError('Original suppliers are read-only')
            path=mapped(path)
        return old_builtin(path,mode,*a,**kw)
    Path.open=path_open;Path.stat=lambda p,*a,**kw:old_stat(mapped(p),*a,**kw)
    Path.exists=lambda p:old_exists(mapped(p));Path.is_file=lambda p:old_is_file(mapped(p));builtins.open=builtin_open
    try:yield aliases
    finally:Path.open=old_open;Path.stat=old_stat;Path.exists=old_exists;Path.is_file=old_is_file;builtins.open=old_builtin
