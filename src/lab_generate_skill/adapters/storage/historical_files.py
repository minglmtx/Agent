"""Bounded descriptor-relative reads inside a canonical trusted reference root.

No component follows links; first error and descriptor close failures survive.
Cooperative checkpoints do not replace runtime hard-I/O supervision.
"""

import hashlib
import os
import stat
from pathlib import Path, PurePosixPath
from lab_generate_skill.adapters.releases.artifact_copy import close_all
from lab_generate_skill.domain.errors import EvidenceIntegrityError, EvidenceNotFound
from lab_generate_skill.ports.lifecycle import OperationControl


def read_historical_file(
    root: Path,
    relative: str,
    sha256: str,
    limit: int,
    control: OperationControl,
    *,
    exact_size: int | None = None,
) -> bytes:
    parts = PurePosixPath(relative).parts
    if (
        not root.is_absolute()
        or not parts
        or PurePosixPath(relative).is_absolute()
        or ".." in parts
        or str(PurePosixPath(relative)) != relative
    ):
        raise ValueError("Historical file needs canonical root and relative name")
    control.checkpoint()
    if root.resolve(strict=True) != root:
        raise EvidenceIntegrityError("Historical root cannot be a symlink alias")
    descriptors: list[int] = []
    primary: BaseException | None = None
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(directory)
        for part in parts[:-1]:
            control.checkpoint()
            directory = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            descriptors.append(directory)
        fd = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        descriptors.append(fd)
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or not 0 <= before.st_size <= limit
            or (exact_size is not None and before.st_size != exact_size)
        ):
            raise EvidenceIntegrityError("Historical file type/size differs from pin")
        content = bytearray()
        digest = hashlib.sha256()
        while True:
            control.checkpoint()
            chunk = os.read(fd, min(1024 * 1024, limit + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
            digest.update(chunk)
            if len(content) > limit:
                raise EvidenceIntegrityError("Historical file grew beyond bound")
        after = os.fstat(fd)
        current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)

        def state(s: os.stat_result) -> tuple[int, int, int, int, int]:
            return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns

        if (
            state(before) != state(after)
            or state(after) != state(current)
            or digest.hexdigest() != sha256
            or len(content) != before.st_size
        ):
            raise EvidenceIntegrityError(
                "Historical bytes changed or do not match original digest"
            )
        control.checkpoint()
        return bytes(content)
    except FileNotFoundError as error:
        primary = EvidenceNotFound("Historical workspace copy is missing")
        raise primary from error
    except BaseException as error:
        primary = error
        raise
    finally:
        close_all(tuple(reversed(descriptors)), primary)
