"""Stable same-UID lock namespace; never unlink locks or replace their inode.

Synchronous local file primitives, for a registered supervised worker only.
Cooperating processes share one namespace regardless of run/release/task ID.
The existing node namespace is retained across caller migration; historical
read bits are harmless below its private 0700 directory. New files are 0600.
This is not protection from a hostile same-UID process or a network namespace.
"""

import os
from pathlib import Path
import stat


def namespace() -> Path:
    return Path("/tmp") / f"lab-admin-ports-{os.getuid()}"


def validate_file(fd: int) -> None:
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) not in (0o600, 0o640, 0o604, 0o644)
        or info.st_nlink != 1
    ):
        raise ValueError("Expected private single-link port lock file")


def close_descriptors(descriptors: list[int]) -> list[BaseException]:
    errors: list[BaseException] = []
    while descriptors:
        fd = descriptors.pop()
        try:
            os.close(fd)
        except BaseException as error:
            # On Linux close may already have consumed the fd. Never retry it.
            errors.append(error)
    return errors


def open_namespace() -> int:
    path = namespace()
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if (
            info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            or path.stat(follow_symlinks=False).st_ino != info.st_ino
        ):
            raise ValueError("Expected original private node-local port namespace")
        return fd
    except BaseException as primary:
        errors = close_descriptors([fd])
        if errors:
            raise BaseExceptionGroup(
                "Port namespace validation and close failed", [primary, *errors]
            ) from None
        raise
