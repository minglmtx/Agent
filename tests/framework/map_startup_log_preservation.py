"""Preserve this engineering instance's closed startup logs before job /tmp ends."""

import hashlib
import os
from pathlib import Path
import stat
from typing import Any
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.service_commands import SERVICE_NAMES


def preserve_closed_startup_logs(
    parent: Path, destination: Path, control: OperationControl
) -> dict[str, Any]:
    """Caller must first prove the original resource domain closed; no service I/O."""
    control.checkpoint()
    if not parent.is_absolute() or parent.resolve(strict=True) != parent:
        raise ValueError("Original private Map parent required")
    if parent.stat().st_uid != os.getuid() or not parent.is_dir():
        raise ValueError("Original owned private Map parent required")
    paths: list[tuple[str, Path]] = []
    absent = []
    for service in SERVICE_NAMES:
        source = (
            parent / "instance/logs/generation-1" / f"{service}-1" / f"{service}.log"
        )
        if not os.path.lexists(source):
            absent.append(service)
            continue
        if source.resolve(strict=True) != source:
            raise ValueError("Original startup logs cannot cross symbolic paths")
        info = source.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("Original owned regular startup log required")
        paths.append((service, source))
    control.checkpoint()
    destination.mkdir(mode=0o700)
    rows = []
    for service, source in paths:
        control.checkpoint()
        before = source.stat()
        target = destination / f"{service}.log"
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as reader, target.open("xb") as writer:
            while True:
                control.checkpoint()
                chunk = reader.read(256 * 1024)
                if not chunk:
                    break
                writer.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        after = source.stat()
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or size != before.st_size:
            raise ValueError("Original closed startup log changed during preservation")
        rows.append(
            dict(
                service=service,
                source=str(source),
                path=str(target),
                bytes=size,
                sha256=digest.hexdigest(),
            )
        )
    control.checkpoint()
    return dict(
        present_logs_saved_completely=True,
        original_parent=str(parent),
        logs=rows,
        absent_services=absent,
    )
