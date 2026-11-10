"""Linux tool-process isolation for this benchmark, not a product feature.
Landlock restricts file contents; seccomp denies sockets and cross-process reads.
Requires Linux Landlock ABI >= 3, x86_64. Fail closed if unavailable.
"""
import ctypes as C
import errno
import os
import platform
from pathlib import Path


def restrict(read_paths, write_paths):
    if platform.machine() != 'x86_64':
        raise RuntimeError('sandbox only validated on x86_64')
    libc = C.CDLL(None, use_errno=True)
    def checked(value):
        if value < 0:
            raise OSError(C.get_errno(), os.strerror(C.get_errno()))
        return value
    abi = checked(libc.syscall(444, 0, 0, 1))
    if abi < 3:
        raise RuntimeError(f'Landlock ABI {abi} lacks truncate restriction')
    class Ruleset(C.Structure):
        _fields_ = [('handled_access_fs', C.c_uint64)]
    class PathRule(C.Structure):
        _pack_ = 1
        _fields_ = [('allowed_access', C.c_uint64), ('parent_fd', C.c_int32)]
    handled = (1 << 15) - 1
    rs = Ruleset(handled)
    fd = checked(libc.syscall(444, C.byref(rs), C.sizeof(rs), 0))
    try:
        for path, writable in [(p, False) for p in read_paths] + [(p, True) for p in write_paths]:
            path = Path(path).resolve()
            if not path.exists():
                continue
            access = handled if writable else (1 | 4 | 8)
            if not path.is_dir():
                access &= 1 | 2 | 4 | (1 << 14)
            pfd = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathRule(access, pfd)
                checked(libc.syscall(445, fd, 1, C.byref(rule), 0))
            finally:
                os.close(pfd)
        checked(libc.prctl(38, 1, 0, 0, 0))  # no_new_privs, inherited
        checked(libc.syscall(446, fd, 0))
    finally:
        os.close(fd)
    # Deny new sockets/connects; preserve socketpair for asyncio's self-pipe.
    # Also deny ptrace/process_vm, io_uring (network bypass), mount, and BPF.
    denied = [41, 42, 101, 165, 166, 298, 310, 311, 321, 425, 426, 427]
    class Filter(C.Structure):
        _fields_ = [('code', C.c_ushort), ('jt', C.c_ubyte), ('jf', C.c_ubyte), ('k', C.c_uint)]
    class Program(C.Structure):
        _fields_ = [('len', C.c_ushort), ('filter', C.POINTER(Filter))]
    instructions = [Filter(0x20, 0, 0, 4), Filter(0x15, 1, 0, 0xc000003e), Filter(0x06, 0, 0, 0x80000000), Filter(0x20, 0, 0, 0)]
    # Reject x32 ABI as well as other architectures.
    instructions += [Filter(0x35, 0, 1, 0x40000000), Filter(0x06, 0, 0, 0x00050000 | errno.EPERM)]
    for syscall in denied:
        instructions += [Filter(0x15, 0, 1, syscall), Filter(0x06, 0, 0, 0x00050000 | errno.EPERM)]
    instructions += [Filter(0x06, 0, 0, 0x7fff0000)]
    array = (Filter * len(instructions))(*instructions)
    prog = Program(len(instructions), array)
    checked(libc.prctl(22, 2, C.byref(prog), 0, 0))
    return abi


def runtime_reads():
    return ['/usr', '/lib', '/lib64', '/bin', '/sbin', '/etc/ld.so.cache', '/etc/localtime', '/dev/urandom', '/dev/random']
