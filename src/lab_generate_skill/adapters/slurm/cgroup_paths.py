"""Shared root-managed control-path and stable-mount checks for live/empty trees."""

import os
from pathlib import Path
import stat

from .cgroup_codec import CgroupMount
from .kernel_capture import KernelReadings
from .kernel_files import KernelControl


def inspect_cgroup_chain(
    readings: KernelReadings, leaf: Path, mount: CgroupMount
) -> dict[Path, KernelControl]:
    root = Path("/sys/fs/cgroup")
    if not leaf.is_relative_to(root) or ".." in leaf.parts:
        raise ValueError("Cgroup control path must be inside the fixed mount")
    identities: dict[Path, KernelControl] = {}
    for path in tuple(reversed(leaf.parents)) + (leaf,):
        identity = readings.inspect(path, directory=True)
        identities[path] = identity
        if path == root or path.is_relative_to(root):
            if (os.major(identity.device), os.minor(identity.device)) != (
                mount.major,
                mount.minor,
            ):
                raise ValueError("Cgroup directory is not on the observed kernel mount")
            for name in ("cgroup.procs", "cgroup.threads"):
                record = readings.inspect(path / name, directory=False)
                if record.device != identity.device:
                    raise ValueError("Cgroup control is on another filesystem")
    return identities


def recheck_controls(readings: KernelReadings) -> None:
    for identity in tuple(readings.controls):
        if (
            readings.inspect(Path(identity.path), directory=stat.S_ISDIR(identity.mode))
            != identity
        ):
            raise ValueError("Original cgroup path identity changed")
