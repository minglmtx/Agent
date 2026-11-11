"""Node-local cooperative leases for all five private website service ports.

Keep locks for the parent worker's lifetime. Pick outside Linux's ephemeral
client-port range, so outgoing requests cannot take ports during slow startup.
No service or other job is killed or rebound by this allocator.
"""
import atexit
import fcntl
import os
from pathlib import Path
import random
import socket

class PortLease:
    def __init__(self,count=5,directory=None):
        self.handles=[];self.ports=[]
        directory=Path(directory or ('/tmp/lab-admin-ports-'+str(os.getuid())))
        directory.mkdir(mode=0o700,exist_ok=True)
        if directory.stat().st_uid!=os.getuid():raise RuntimeError('Port lease directory ownership mismatch')
        lo,hi=map(int,Path('/proc/sys/net/ipv4/ip_local_port_range').read_text().split())
        candidates=[x for x in range(10000,30000) if x != 10080 and not lo<=x<=hi]
        random.SystemRandom().shuffle(candidates)
        try:
            for port in candidates:
                handle=(directory/str(port)).open('a+')
                try:
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    with socket.socket() as probe:probe.bind(('127.0.0.1',port))
                except (BlockingIOError,OSError):handle.close();continue
                self.handles.append(handle);self.ports.append(port)
                if len(self.ports)==count:break
            if len(self.ports)!=count:raise RuntimeError('No free private website port leases')
        except BaseException:self.close();raise
    def close(self):
        for handle in self.handles:handle.close()
        self.handles=[]
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

_lease=None

def reserve_website_ports():
    global _lease
    if _lease is None:
        _lease=PortLease();atexit.register(_lease.close)
    os.environ['WA_FIXED_PORTS']=' '.join(map(str,_lease.ports[:3]))
    os.environ['WA_FIXED_SEARCH_PORTS']=' '.join(map(str,_lease.ports[3:]))
    return tuple(_lease.ports)
