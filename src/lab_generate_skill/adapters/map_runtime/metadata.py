"""Bounded original pinned metadata reads, preserving parse and close failures."""

import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.map_runtime_inputs import MAX_METADATA_BYTES
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.artifact_copy import close_all


def read_pinned_bytes(path: Path, pin: ReleaseFile, control: OperationControl) -> bytes:
    pin = ReleaseFile.model_validate(pin)
    control.checkpoint()
    if (
        not 0 < pin.size_bytes <= MAX_METADATA_BYTES
        or pin.executable
        or path.name != pin.path
        or path.resolve(strict=True) != path
    ):
        raise EvidenceIntegrityError("Original canonical bounded metadata required")
    fd: int | None = None
    primary: BaseException | None = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size != pin.size_bytes
            or before.st_mode & 0o111
        ):
            raise EvidenceIntegrityError(
                "Metadata type/size/executable differs from pin"
            )
        chunks = []
        remaining = pin.size_bytes + 1
        while remaining:
            control.checkpoint()
            part = os.read(fd, min(256 * 1024, remaining))
            if not part:
                break
            chunks.append(part)
            remaining -= len(part)
        after = os.fstat(fd)
        named = path.lstat()
        data = b"".join(chunks)
        if (
            remaining != 1
            or hashlib.sha256(data).hexdigest() != pin.sha256
            or (named.st_dev, named.st_ino) != (after.st_dev, after.st_ino)
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
            raise EvidenceIntegrityError("Original metadata content/identity changed")
        control.checkpoint()
        return data
    except BaseException as error:
        primary = error
        raise
    finally:
        close_all((fd,), primary)


def object_json(data: bytes) -> dict[str, Any]:
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("Repeated original JSON field")
            result[key] = value
        return result

    def constant(value: str) -> Any:
        raise ValueError("Non-finite JSON value is not original metadata")

    value = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        raise ValueError("Original metadata JSON object required")
    return value
