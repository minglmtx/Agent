"""Read the original closed generation's owned bounded Gitaly log exactly once."""

import hashlib
import os
import stat
from pathlib import Path
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.ports.lifecycle import OperationControl
from .shutdown_contract import GitalyTermExit
from .service_files import checked
from .workhorse_shutdown import WorkhorseTermExit, MAX_LOG_BYTES


def read_original_log(path: Path, limit: int, control: OperationControl) -> bytes:
    checked(path, control)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or not 0 < before.st_size <= limit
        ):
            raise ValueError(
                "Original closed service log is not bounded owned regular bytes"
            )
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(raw) != before.st_size:
        raise ValueError("Original closed service log changed during read")
    control.checkpoint()
    return raw


def read_workhorse_term_exit(
    root: Path,
    original: NativeNamespaceIdentity,
    image_sha256: str,
    control: OperationControl,
) -> WorkhorseTermExit:
    if original.service not in ("workhorse", "workhorse-internal"):
        raise ValueError("Original fixed Workhorse service required")
    return WorkhorseTermExit.from_raw(
        original,
        image_sha256,
        read_original_log(root / (original.service + ".log"), MAX_LOG_BYTES, control),
    )


def read_gitaly_term_exit(
    root: Path,
    original: NativeNamespaceIdentity,
    image_sha256: str,
    control: OperationControl,
) -> GitalyTermExit:
    path = root / "gitaly.log"
    raw = read_original_log(path, 65536, control)
    return GitalyTermExit(
        original=original,
        image_sha256=image_sha256,
        log_bytes=len(raw),
        log_sha256=hashlib.sha256(raw).hexdigest(),
        log=raw.decode("utf-8"),
    )
