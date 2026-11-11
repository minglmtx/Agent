"""Exact Linux x86-64 pidfd ABI, including Python builds without os.pidfd_open.

No PID signalling fallback or syscall retry. ENOSYS/permission/identity errors
remain errors. Numbers are fixed by Linux v6.6 arch/x86/entry/syscalls/syscall_64.tbl:
https://github.com/torvalds/linux/blob/v6.6/arch/x86/entry/syscalls/syscall_64.tbl
Only the current cluster ABI is implemented; reject other/32-bit architectures.
"""

import ctypes
import os
import signal
import sys


def _call(number: int, *args: object) -> int:
    if (
        sys.platform != "linux"
        or os.uname().machine != "x86_64"
        or ctypes.sizeof(ctypes.c_void_p) != 8
    ):
        raise RuntimeError("pidfd adapter requires Linux x86-64")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    result = int(libc.syscall(ctypes.c_long(number), *args))
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, "Original pidfd syscall failed")
    return result


def open_pidfd(pid: int) -> int:
    if type(pid) is not int or not 0 < pid < 2**31:
        raise ValueError("pidfd requires a positive Linux PID")
    return _call(434, ctypes.c_int(pid), ctypes.c_uint(0))


def kill_pidfd(fd: int) -> None:
    if type(fd) is not int or not 0 <= fd < 2**31:
        raise ValueError("pidfd requires an owned nonnegative descriptor")
    _call(
        424,
        ctypes.c_int(fd),
        ctypes.c_int(signal.SIGKILL),
        ctypes.c_void_p(),
        ctypes.c_uint(0),
    )
