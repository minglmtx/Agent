"""Local file handles and chunked copying for quiesced private artifact trees.

Only the owning supervised worker may call these synchronous operations.
Checkpoints do not make kernel I/O interruptible. No symlinks/special files or
multiply linked files are accepted; external concurrent mutation is not supported.
"""

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import stat
from lab_generate_skill.ports.lifecycle import OperationControl

CHUNK_BYTES = 1024 * 1024


def checked_path(path: Path, control: OperationControl) -> None:
    """Reject links/non-directory ancestors, including above the declared root."""
    for part in (*reversed(path.parents), path):
        control.checkpoint()
        try:
            mode = part.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode) or (part != path and not stat.S_ISDIR(mode)):
            raise ValueError("Unsafe artifact path component")


@contextmanager
def held_file(path: Path, flags: int) -> Iterator[int]:
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    primary: BaseException | None = None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Artifact file must be regular and singly linked")
        yield fd
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            os.close(fd)
        except BaseException as cleanup:
            if primary is not None:
                raise BaseExceptionGroup(
                    "Artifact I/O and close failed", [primary, cleanup]
                ) from None
            raise


def identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def copy_file(source: Path, target: Path, control: OperationControl) -> None:
    control.checkpoint()
    with held_file(source, os.O_RDONLY) as src:
        before = os.fstat(src)
        with held_file(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL) as dst:
            while True:
                control.checkpoint()
                block = os.read(src, CHUNK_BYTES)
                if not block:
                    break
                view = memoryview(block)
                while view:
                    control.checkpoint()
                    count = os.write(dst, view)
                    if count <= 0:
                        raise OSError("Artifact copy made no progress")
                    view = view[count:]
            if identity(before) != identity(os.fstat(src)) or identity(
                before
            ) != identity(source.lstat()):
                raise ValueError("Artifact changed during copy")
            os.fchmod(dst, stat.S_IMODE(before.st_mode))
            os.fsync(dst)
