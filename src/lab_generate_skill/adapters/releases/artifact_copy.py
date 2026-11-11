"""Copy one explicitly pinned regular file; retain primary and all close errors."""

import hashlib
import os
import stat
from pathlib import Path

from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl


def close_all(
    descriptors: tuple[int | None, ...], primary: BaseException | None
) -> None:
    errors: list[Exception] = []
    for fd in descriptors:
        if fd is not None:
            try:
                os.close(fd)
            except OSError as error:
                errors.append(error)
    if errors:
        if primary is not None:
            raise BaseExceptionGroup(
                "Artifact operation and close failed", [primary, *errors]
            ) from None
        raise ExceptionGroup("Artifact close failed", errors)


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    primary: BaseException | None = None
    try:
        os.fsync(fd)
    except BaseException as error:
        primary = error
        raise
    finally:
        close_all((fd,), primary)


def sync_regular_file(path: Path) -> None:
    if path.resolve(strict=True) != path:
        raise EvidenceIntegrityError("Artifact durability path uses an alias")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    primary: BaseException | None = None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise EvidenceIntegrityError("Artifact durability requires a regular file")
        os.fsync(fd)
    except BaseException as error:
        primary = error
        raise
    finally:
        close_all((fd,), primary)


FileIdentity = tuple[int, int, int, int, int, int]


def file_identity(info: os.stat_result) -> FileIdentity:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_mode,
    )


def copy_pinned_file(
    source_root: Path,
    target_root: Path,
    entry: ReleaseFile,
    control: OperationControl,
    *,
    final_mode: int | None = None,
    source_identity: FileIdentity | None = None,
) -> None:
    if final_mode is not None and (
        type(final_mode) is not int
        or not 0 <= final_mode <= 0o777
        or not final_mode & 0o400
        or bool(final_mode & 0o111) != entry.executable
    ):
        raise ValueError(
            "Final declared file mode differs from readable/executable pin"
        )
    if source_identity is not None and (
        type(source_identity) is not tuple
        or len(source_identity) != 6
        or any(type(value) is not int for value in source_identity)
    ):
        raise ValueError("Exact original preflight file identity required")
    source, target = source_root / entry.path, target_root / entry.path
    if (
        source.resolve(strict=True) != source
        or target.parent.resolve(strict=True) != target.parent
    ):
        raise EvidenceIntegrityError("Artifact copy path uses an alias")
    source_fd: int | None = None
    target_fd: int | None = None
    primary: BaseException | None = None
    try:
        control.checkpoint()
        source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(source_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size != entry.size_bytes
            or bool(before.st_mode & 0o111) != entry.executable
        ):
            raise EvidenceIntegrityError(
                "Copy source type/size/executable differs from pin"
            )
        if source_identity is not None and file_identity(before) != source_identity:
            raise EvidenceIntegrityError(
                "Copy source changed after whole-tree preflight"
            )
        target_fd = os.open(
            target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
        )
        digest = hashlib.sha256()
        remaining = entry.size_bytes + 1
        while remaining:
            control.checkpoint()
            chunk = os.read(source_fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                control.checkpoint()
                count = os.write(target_fd, view)
                if count <= 0:
                    raise OSError("Artifact write made no progress")
                view = view[count:]
        after = os.fstat(source_fd)
        if (
            remaining != 1
            or digest.hexdigest() != entry.sha256
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
        ):
            raise EvidenceIntegrityError("Copy source bytes or identity changed")
        os.fchmod(
            target_fd,
            (
                final_mode
                if final_mode is not None
                else (0o555 if entry.executable else 0o444)
            ),
        )
        os.fsync(target_fd)
        control.checkpoint()
    except BaseException as error:
        primary = error
        raise
    finally:
        close_all((target_fd, source_fd), primary)
