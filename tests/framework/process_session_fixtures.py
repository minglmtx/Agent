"""Standard-library-only child fixtures; no imports of project or model runtime."""

import sys
from lab_generate_skill.adapters.processes.session import FramedProcessSession

CHILD = r"""
import os,struct,sys,time

def read(n):
    out=b''
    while len(out)<n:
        raw=os.read(0,n-len(out))
        if not raw:raise EOFError()
        out+=raw
    return out

def send(raw):
    value=struct.pack('>I',len(raw))+raw
    while value:
        count=os.write(1,value[:4096]);value=value[count:]

while True:
    try:
        size=struct.unpack('>I',read(4))[0]
        raw=read(size)
    except EOFError:break
    if raw==b'close':send(b'closed');break
    if raw==b'pid':send(str(os.getpid()).encode());continue
    if raw==b'environment':
        import json
        send(json.dumps({k:os.environ.get(k) for k in ('OPENROUTER_API_KEY','PYTHONPATH','CUDA_VISIBLE_DEVICES')},sort_keys=True).encode());continue
    if raw==b'stall':time.sleep(30);continue
    if raw==b'partial':os.write(1,b'\x00\x00\x00\x05xx');break
    if raw==b'oversize':os.write(1,struct.pack('>I',2**32-1));continue
    if raw==b'trailing':os.write(1,struct.pack('>I',1)+b'xy');continue
    if raw==b'crash':os.write(2,b'complete error sentinel');sys.exit(3)
    if raw==b'stderr':
        os.write(2,b'warning-before-reply\n');send(b'ok');continue
    if raw==b'flood':
        while True:os.write(2,b'x'*4096)
    send(raw)
"""


def session(
    *, source: str = CHILD, limit: int = 2 * 1024 * 1024, stderr_limit: int = 4096
) -> FramedProcessSession:
    return FramedProcessSession(
        (sys.executable, "-I", "-B", "-c", source),
        max_frame_bytes=limit,
        max_stderr_bytes=stderr_limit,
        cuda_visible_devices="0",
    )
