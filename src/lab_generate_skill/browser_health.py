"""Local runtime evidence only; never retry browser actions after a crash."""
import os,time,shutil
from pathlib import Path
from .io_utils import append_jsonl
from .runtime_diagnostics import failure_diagnostic


def record(directory,event,exc=None):
    row={'event':event,'at':time.time(),'pid':os.getpid()}
    if exc is not None:row['error']=failure_diagnostic(exc,event)
    try:
        import psutil
        proc=psutil.Process();row['process_rss_bytes']=proc.memory_info().rss
        row['children']=[{'pid':p.pid,'name':p.name(),'rss_bytes':p.memory_info().rss} for p in proc.children(recursive=True) if p.is_running()]
        row['shm_free_bytes']=shutil.disk_usage('/dev/shm').free
        # cgroup counters distinguish observed memory pressure from speculation.
        cg=Path('/proc/self/cgroup').read_text().splitlines()
        for line in cg:
            if line.startswith('0::'):
                root=Path('/sys/fs/cgroup')/line[3:].lstrip('/')
                row['cgroup_memory']={n:(root/n).read_text().strip() for n in ('memory.events','memory.current','memory.max') if (root/n).is_file()}
    except Exception as evidence_error:row['resource_evidence_error']=type(evidence_error).__name__
    append_jsonl(Path(directory)/'browser-health.jsonl',[row])


def attach(page,directory):
    def crashed(*_):
        page._lab_crashed=True
        record(directory,'browser_crash_event')
    page.on('crash',crashed)
    record(directory,'browser_ready')


def require_live_page(page):
    if getattr(page,'_lab_crashed',False):
        raise RuntimeError('Target crashed: refusing further DOM access or action replay')
