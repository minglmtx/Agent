"""Complete immutable member read; shared file primitive, no role or authority.

Call only after the original role-specific permission check, in supervised I/O.
Large opaque weights are verified/copied as streams; this reader is for explicit
full-member consumers and never truncates or changes the declared file bytes.
"""

import hashlib
import os
from pathlib import Path
import stat
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from .artifact_copy import close_all


def frozen_bytes(root: Path, entry: ReleaseFile, control: OperationControl) -> bytes:
    path = root / entry.path
    if path.resolve(strict=True) != path:
        raise EvidenceIntegrityError("Immutable artifact path aliases another file")
    fd: int | None = None
    primary: BaseException | None = None
    try:
        control.checkpoint()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size != entry.size_bytes
            or before.st_mode & 0o222
            or bool(before.st_mode & 0o111) != entry.executable
        ):
            raise EvidenceIntegrityError(
                "Immutable artifact file type/size/mode differs"
            )
        digest = hashlib.sha256()
        chunks = []
        left = entry.size_bytes + 1
        while left:
            control.checkpoint()
            chunk = os.read(fd, min(left, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
            digest.update(chunk)

        def identity(s: os.stat_result) -> tuple[int, ...]:
            return (
                s.st_dev,
                s.st_ino,
                s.st_size,
                s.st_mode,
                s.st_mtime_ns,
                s.st_ctime_ns,
            )

        if (
            left != 1
            or digest.hexdigest() != entry.sha256
            or identity(before) != identity(os.fstat(fd))
            or identity(before) != identity(path.lstat())
            or path.resolve(strict=True) != path
        ):
            raise EvidenceIntegrityError("Immutable artifact bytes or identity changed")
        control.checkpoint()
        return b"".join(chunks)
    except BaseException as error:
        primary = error
        raise
    finally:
        close_all((fd,), primary)
