"""Bounded private copies of stopped immutable service snapshots.

No hard links, symlinks, destination reuse or source writes. Progress includes
counts and bytes only. The service must start only after successful completion.
"""
import os,shutil,stat,time
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from pathlib import Path
from .io_utils import atomic_write_json


def metadata(p):
    s=p.lstat()
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,stat.S_IMODE(s.st_mode))


def clone(source,destination,progress,*,workers=4):
    source=Path(source).resolve(strict=True);destination=Path(destination)
    if type(workers) is not int or not 1<=workers<=4:raise ValueError('One to four copy workers required')
    if destination.exists() or destination.is_symlink():raise ValueError('Existing destination cannot be reused')
    if source==destination.resolve() or source in destination.resolve().parents:raise ValueError('Destination must be outside the source')
    files=[];directories=[source];started=time.monotonic()
    for root,dirs,names in os.walk(source,followlinks=False):
        for name in dirs+names:
            p=Path(root)/name;s=p.lstat()
            if stat.S_ISDIR(s.st_mode):directories.append(p)
            elif stat.S_ISREG(s.st_mode):files.append((p,metadata(p)))
            else:raise ValueError('Snapshot contains a symlink or non-regular object')
    # Verify that the scanned source set remains identical at completion.
    source_directories={p:metadata(p) for p in directories}
    destination.mkdir(parents=False,mode=0o700)
    for p in sorted(directories[1:],key=lambda p:len(p.parts)):
        (destination/p.relative_to(source)).mkdir(mode=0o700)
    total=sum(m[2] for _,m in files);done=0;done_bytes=0
    def report(status):
        atomic_write_json(progress,{'status':status,'workers':workers,'total_files':len(files),'completed_files':done,
            'total_bytes':total,'completed_bytes':done_bytes,'seconds':time.monotonic()-started,
            'source_modified':False if status=='complete' else None,'hardlinks_used':False})
    def copy(item):
        p,before=item;target=destination/p.relative_to(source)
        if metadata(p)!=before:raise RuntimeError('Source changed before copy')
        shutil.copy2(p,target,follow_symlinks=False)
        s=target.stat()
        if metadata(p)!=before or s.st_size!=before[2] or s.st_mtime_ns!=before[3] or stat.S_IMODE(s.st_mode)!=before[5]:
            raise RuntimeError('Source changed or copy metadata verification failed')
        if (s.st_dev,s.st_ino)==before[:2]:raise RuntimeError('Destination aliases source')
        return s.st_size
    report('copying')
    try:
        # Start large files first so a single large tail cannot serialize the end.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending={pool.submit(copy,x) for x in sorted(files,key=lambda x:x[1][2],reverse=True)}
            last_report=time.monotonic()
            while pending:
                finished,pending=wait(pending,timeout=5,return_when=FIRST_COMPLETED)
                for f in finished:done_bytes+=f.result();done+=1
                if time.monotonic()-last_report>=5:
                    report('copying');last_report=time.monotonic()
        for p,before in source_directories.items():
            if metadata(p)!=before:raise RuntimeError('Source directory changed during copy')
        for p in sorted(directories,key=lambda p:len(p.parts),reverse=True):
            shutil.copystat(p,destination/p.relative_to(source),follow_symlinks=False)
        report('complete')
    except BaseException:
        report('failed');raise
