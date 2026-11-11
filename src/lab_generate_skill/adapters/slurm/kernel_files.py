"""Bounded no-follow local kernel reads and root-owned control-path inspection.

Callers select only fixed proc/sys paths, never a caller-supplied alternate
kernel root. OS calls remain cooperative: use external supervision before
production adoption. Errors retain bounded partial bytes and all close errors.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import stat

from lab_generate_skill.adapters.releases.artifact_copy import close_all
from lab_generate_skill.ports.lifecycle import OperationControl


@dataclass(frozen=True)
class KernelRead:
    path: str
    content: bytes
    complete: bool


@dataclass(frozen=True)
class KernelControl:
    path: str
    device: int
    inode: int
    uid: int
    gid: int
    mode: int
    writable: bool


def _open_path(
    path: Path, descriptors: list[int], control: OperationControl, *, directory: bool
) -> int:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Kernel path must be absolute and contain no parent traversal")
    control.checkpoint()
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descriptors.append(parent)
    for index, part in enumerate(path.parts[1:]):
        control.checkpoint()
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        if index < len(path.parts) - 2 or directory:
            flags |= os.O_DIRECTORY
        parent = os.open(part, flags, dir_fd=parent)
        descriptors.append(parent)
    return parent


def read_kernel_file(path: Path, limit: int, control: OperationControl) -> KernelRead:
    if type(limit) is not int or not 1 <= limit <= 1024 * 1024:
        raise ValueError("Kernel read limit must be 1..1MiB")
    descriptors: list[int] = []
    content = bytearray()
    primary: BaseException | None = None
    try:
        try:
            fd = _open_path(path, descriptors, control, directory=False)
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("Kernel record is not a regular pseudo-file")
            while True:
                control.checkpoint()
                chunk = os.read(fd, min(65536, limit + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
                if len(content) > limit:
                    raise ValueError("Kernel record exceeds read bound")
            after = os.fstat(fd)
            current = os.stat(path, follow_symlinks=False)
            if (before.st_dev, before.st_ino, before.st_mode) != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
            ) or (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino):
                raise ValueError("Kernel record identity changed during read")
            control.checkpoint()
        except BaseException as error:
            primary = error
            raise
        finally:
            close_all(tuple(reversed(descriptors)), primary)
    except BaseException as error:
        error.kernel_read_capture = KernelRead(str(path), bytes(content), False)  # type: ignore[attr-defined]
        raise
    return KernelRead(str(path), bytes(content), True)


def inspect_control(
    path: Path, control: OperationControl, *, directory: bool
) -> KernelControl:
    """Inspect root ownership, modes, ACL write access and stable inode."""
    descriptors: list[int] = []
    primary: BaseException | None = None
    result: KernelControl | None = None
    try:
        try:
            fd = _open_path(path, descriptors, control, directory=directory)
            before = os.fstat(fd)
            writable = os.access(
                path, os.W_OK, effective_ids=True, follow_symlinks=False
            )
            result = KernelControl(
                str(path),
                before.st_dev,
                before.st_ino,
                before.st_uid,
                before.st_gid,
                before.st_mode,
                writable,
            )
            if (
                before.st_uid != 0
                or before.st_gid != 0
                or before.st_mode & 0o022
                or writable
                or not (
                    stat.S_ISDIR(before.st_mode)
                    if directory
                    else stat.S_ISREG(before.st_mode)
                )
            ):
                raise ValueError("Cgroup control path is not exclusively root managed")
            after = os.stat(path, follow_symlinks=False)
            if (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_uid,
                before.st_gid,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_uid,
                after.st_gid,
            ):
                raise ValueError("Cgroup control path changed during inspection")
            control.checkpoint()
        except BaseException as error:
            primary = error
            raise
        finally:
            close_all(tuple(reversed(descriptors)), primary)
    except BaseException as error:
        if result is not None:
            error.kernel_control_capture = result  # type: ignore[attr-defined]
        raise
    return result
