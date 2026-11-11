"""Current ordinary bundle launcher binds assets to its reviewed frozen archive."""
from contextlib import contextmanager
import hashlib,json,os,re,tarfile
from pathlib import Path,PurePosixPath
from .native_runtime_assets import preflight,required
SHA=re.compile(r'[0-9a-f]{64}')
MANIFEST='.lab-reviewed-frozen-runtime-file-sha256.json'
META='.lab-reviewed-frozen-runtime-origin.json'
MAX_BYTES=2*1024**3


def pin_actual_extraction(project,archive,expected_sha256):
    root=Path(project).resolve();archive=Path(archive)
    if not isinstance(expected_sha256,str)or not SHA.fullmatch(expected_sha256):raise ValueError('Reviewed runtime archive SHA256 required')
    if not archive.is_absolute()or archive.is_symlink()or not archive.is_file():raise ValueError('Regular actual runtime archive required')
    h=hashlib.sha256()
    with archive.open('rb')as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    if h.hexdigest()!=expected_sha256:raise ValueError('Reviewed runtime archive changed')
    members={};total=0
    with tarfile.open(archive,'r:gz')as tar:
        for entry in tar:
            name=entry.name;p=PurePosixPath(name)
            if (not entry.isfile()or name in members or p.is_absolute()or '..'in p.parts or '\\'in name
                    or name in (MANIFEST,META)):
                raise ValueError('Unique safe regular frozen runtime members required')
            total+=entry.size
            if total>MAX_BYTES:raise ValueError('Bounded complete runtime required')
            actual=root/name
            if actual.is_symlink()or not actual.is_file()or root not in actual.resolve().parents:
                raise ValueError('Actual frozen extraction missing member: '+name)
            data=tar.extractfile(entry).read()
            if len(data)!=entry.size or actual.read_bytes()!=data:raise ValueError('Actual runtime extraction differs: '+name)
            members[name]=hashlib.sha256(data).hexdigest()
    if not members:raise ValueError('Nonempty actual runtime required')
    path=root/MANIFEST;payload=(json.dumps(members,sort_keys=True,indent=2)+'\n').encode()
    # Resuming a launcher may reuse exactly the same metadata. Different bytes
    # never overwrite an old declaration or hide a changed frozen runtime.
    for target,value in ((path,payload),(root/META,(json.dumps({'version':'actual-frozen-runtime-asset-origin-v1','archive':str(archive),'archive_sha256':expected_sha256,'regular_members':len(members)},sort_keys=True,indent=2)+'\n').encode())):
        if target.exists():
            if target.is_symlink()or not target.is_file()or target.read_bytes()!=value:raise ValueError('Frozen origin declaration changed')
        else:
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb')as stream:stream.write(value);stream.flush();os.fsync(stream.fileno())
    return path


@contextmanager
def bind(project,contracts,*,archive=None,archive_sha256=None):
    if bool(archive) != bool(archive_sha256):raise ValueError('Runtime packet and reviewed SHA must be supplied together')
    prior=os.environ.get('LAB_FROZEN_NATIVE_ASSET_MANIFEST');manifest=prior
    if archive is not None:manifest=str(pin_actual_extraction(project,archive,archive_sha256))
    report=preflight(project,contracts,manifest_path=manifest)
    if manifest is not None:os.environ['LAB_FROZEN_NATIVE_ASSET_MANIFEST']=manifest
    try:yield report
    finally:
        if prior is None:os.environ.pop('LAB_FROZEN_NATIVE_ASSET_MANIFEST',None)
        else:os.environ['LAB_FROZEN_NATIVE_ASSET_MANIFEST']=prior
