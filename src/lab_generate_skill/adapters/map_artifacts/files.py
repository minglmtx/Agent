"""Exact owned private roots and durable exclusive byte writes; keep partial files."""

import hashlib
import os
from pathlib import Path
import stat
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.artifact_copy import close_all, sync_directory


def private_directory(path: Path) -> None:
    s = path.lstat()
    if (
        path.resolve(strict=True) != path
        or not stat.S_ISDIR(s.st_mode)
        or s.st_uid != os.getuid()
        or s.st_mode & 0o077
    ):
        raise EvidenceIntegrityError("Original owned private directory required")


def write_once(
    root: Path,
    name: str,
    data: bytes,
    control: OperationControl,
    *,
    readonly: bool = False,
) -> ReleaseFile:
    fd: int | None = None
    primary: BaseException | None = None
    try:
        control.checkpoint()
        if root.resolve(strict=True) != root:
            raise EvidenceIntegrityError("Private file parent aliases another path")
        fd = os.open(
            root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        view = memoryview(data)
        digest = hashlib.sha256()
        while view:
            control.checkpoint()
            chunk = view[: 1024 * 1024]
            count = os.write(fd, chunk)
            if count <= 0:
                raise OSError("Private artifact write made no progress")
            digest.update(chunk[:count])
            view = view[count:]
        if readonly:
            os.fchmod(fd, 0o444)
        os.fsync(fd)
        sync_directory(root)
        control.checkpoint()
        return ReleaseFile(
            path=name, sha256=digest.hexdigest(), size_bytes=len(data), executable=False
        )
    except BaseException as error:
        primary = error
        raise
    finally:
        close_all((fd,), primary)
