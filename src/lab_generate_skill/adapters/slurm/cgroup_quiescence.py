"""Observe the original dedicated-step user subtree after its writer exits.

Read only: no signals, alternate roots, discovery, resets or release permission.
Missing original cgroup paths remain unknown, never an empty-tree observation.
Synchronous kernel reads require external supervision in production.
"""

from dataclasses import dataclass
import errno
import os
from pathlib import Path

from lab_generate_skill.adapters.processes.worker_identity import parse_process_start
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.domain.slurm_quiescence import (
    SlurmUserQuiescence,
    SlurmUserRemoval,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from .cgroup_codec import check_quiescent, parse_mount
from .cgroup_paths import inspect_cgroup_chain, recheck_controls
from .kernel_capture import KernelCapture, KernelReadings
from .kernel_identity import read_process_identity


@dataclass(frozen=True)
class KernelQuiescenceObservation:
    facts: SlurmUserQuiescence | SlurmUserRemoval
    capture: KernelCapture


def _writer_start(
    readings: KernelReadings, original: SlurmCgroupMembership
) -> int | None:
    pid = original.writer.process_id
    try:
        raw = readings.read(Path("/proc") / str(pid) / "stat", 16384)
    except FileNotFoundError as error:
        # Never swallow an exception group containing ENOENT and a close error.
        if error.errno != errno.ENOENT:
            raise
        return None
    start = parse_process_start(raw, pid)
    if start == original.writer.start_ticks:
        raise ValueError("Original writer incarnation still exists")
    return start


def observe_user_quiescence(
    original: SlurmCgroupMembership, control: OperationControl
) -> KernelQuiescenceObservation:
    original = SlurmCgroupMembership.model_validate(original)
    readings = KernelReadings(control)
    try:
        control.checkpoint()
        if original.step_id == "batch":
            raise ValueError("Quiescence requires an original dedicated numeric step")
        observer = read_process_identity(readings, os.getpid(), original.uid)
        if (observer.node_id, observer.boot_id) != (
            original.writer.node_id,
            original.writer.boot_id,
        ):
            raise ValueError(
                "Original user subtree must be observed on the same host boot"
            )
        mount_path = Path("/proc") / str(observer.process_id) / "mountinfo"
        mount = parse_mount(readings.read(mount_path, 1024 * 1024))
        if (mount.mount_id, os.makedev(mount.major, mount.minor)) != (
            original.mount_id,
            original.device,
        ):
            raise ValueError("Original cgroup mount identity differs")
        user = Path(original.user_path)
        identities = inspect_cgroup_chain(readings, user, mount)
        if identities[user].inode != original.user_inode:
            raise ValueError("Original user subtree inode differs")
        before = _writer_start(readings, original)
        # Check recursively reported population, not just this directory's procs.
        for _ in range(2):
            if readings.read(user / "cgroup.type", 4096) != b"domain\n":
                raise ValueError("Threaded or unknown cgroup layout is unsupported")
            check_quiescent(readings.read(user / "cgroup.events", 4096))
            for name in ("cgroup.procs", "cgroup.threads"):
                if readings.read(user / name, 65536) != b"":
                    raise ValueError(
                        "Original user subtree contains processes or threads"
                    )
        after = _writer_start(readings, original)
        if before != after:
            raise ValueError("Original PID observation changed during quiescence check")
        recheck_controls(readings)
        if (
            parse_mount(readings.read(mount_path, 1024 * 1024)) != mount
            or read_process_identity(readings, os.getpid(), original.uid) != observer
        ):
            raise ValueError("Observer identity or mount changed during observation")
        control.checkpoint()
        facts = SlurmUserQuiescence(
            original=original,
            observer=observer,
            writer_status="missing" if after is None else "reused",
            replacement_start_ticks=after,
        )
        return KernelQuiescenceObservation(facts, readings.capture())
    except BaseException as error:
        error.slurm_kernel_capture = readings.capture()  # type: ignore[attr-defined]
        raise
