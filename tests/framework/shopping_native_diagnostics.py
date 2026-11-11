"""Persist actual failed native command bytes, without printing private payloads."""

import base64
from dataclasses import asdict
import json
import os
import stat
from pathlib import Path
from lab_generate_skill.adapters.processes.capture import retained_capture
from lab_generate_skill.domain.site_files import SiteFilesPlan


def retain_native_failure(output: Path, error: BaseException) -> Path | None:
    capture = retained_capture(error)
    if capture is None:
        return None
    value = asdict(capture)
    for key in ("stdout", "stderr"):
        value[key + "_base64"] = base64.b64encode(value.pop(key)).decode("ascii")
    path = output / "failed-native-command.json"
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
    path.chmod(0o600)
    return path


def retain_startup_logs(plan: SiteFilesPlan, output: Path) -> list[dict[str, object]]:
    """Bounded original log tails, called after original domain closure only.

    A missing path is recorded as missing in this job's view, never deletion or
    recovery proof. This helper grants no lifecycle or filesystem authority.
    """
    target = output / "startup-logs"
    target.mkdir(mode=0o700)
    root = Path(plan.node_root)
    if root.is_symlink():
        raise ValueError("Original instance diagnostic root is a symlink")
    if not root.exists():
        return [{"source": "instance", "status": "missing_in_original_job_view"}]
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("Original instance diagnostic ownership changed")
    retained: list[dict[str, object]] = []
    for name in ("logs", "runtime"):
        source = root / name
        if source.is_symlink():
            raise ValueError("Original diagnostic subtree is a symlink")
        if not source.exists():
            retained.append({"source": name, "status": "missing_in_original_job_view"})
            continue
        for path in sorted(source.rglob("*")):
            mode = path.lstat()
            if stat.S_ISLNK(mode.st_mode):
                raise ValueError("Original diagnostic path is a symlink")
            if stat.S_ISDIR(mode.st_mode):
                continue
            if not path.name.endswith(".log"):
                continue
            if not stat.S_ISREG(mode.st_mode) or mode.st_nlink != 1:
                raise ValueError("Unexpected original diagnostic log entry")
            if len(retained) >= 64:
                raise ValueError("Startup log inventory exceeds diagnostic bound")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                stream.seek(max(0, before.st_size - 256 * 1024))
                raw = stream.read(256 * 1024)
                after = os.fstat(stream.fileno())
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise ValueError(
                    "Original closed-domain diagnostic changed during read"
                )
            relative = path.relative_to(root)
            destination = target / relative
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(raw)
            destination.chmod(0o600)
            retained.append(
                {
                    "source": str(relative),
                    "source_bytes": before.st_size,
                    "tail_bytes": len(raw),
                    "truncated": before.st_size > len(raw),
                }
            )
    return retained
