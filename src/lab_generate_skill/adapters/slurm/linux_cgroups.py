"""Observe a known local writer in a fixed host Slurm cgroup-v2 deployment.

No process discovery, signalling, cgroup writes, alternate roots or takeover.
Failure carries partial raw observations for the caller's private evidence
store. This synchronous kernel primitive needs external supervision in the
production resource chain; checkpoint calls are not hard I/O timeouts.
"""

from dataclasses import dataclass
import os
from pathlib import Path

from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.ports.lifecycle import OperationControl

from .cgroup_codec import (
    CgroupMount,
    check_populated,
    check_task_processes,
    parse_membership,
    parse_mount,
)
from .kernel_capture import KernelCapture, KernelReadings
from .kernel_identity import check_observer, read_process_identity
from .cgroup_paths import inspect_cgroup_chain, recheck_controls


@dataclass(frozen=True)
class KernelCgroupObservation:
    membership: SlurmCgroupMembership
    capture: KernelCapture


def _writer_snapshot(
    readings: KernelReadings, execution: SlurmExecutionIdentity, writer: ProcessIdentity
) -> tuple[str, str, CgroupMount, CgroupMount]:
    if os.getpid() != writer.process_id:
        check_observer(readings, execution.uid)
    actual = read_process_identity(readings, writer.process_id, execution.uid)
    proc = Path("/proc") / str(writer.process_id)
    if actual != writer:
        raise ValueError("Writer incarnation changed or differs from original identity")
    step, user = parse_membership(
        readings.read(proc / "cgroup", 4096), execution.raw_job_id
    )
    mount = parse_mount(readings.read(proc / "mountinfo", 1024 * 1024))
    observer_mount = mount
    if writer.process_id != os.getpid():
        observer_mount = parse_mount(
            readings.read(Path("/proc") / str(os.getpid()) / "mountinfo", 1024 * 1024)
        )
        # Mount IDs are local to mount instances, not cgroup superblock IDs.
        # Both parsers require the full root at the canonical mountpoint.
        if (observer_mount.major, observer_mount.minor) != (mount.major, mount.minor):
            raise ValueError("Writer and observer cgroup mounts differ")
    # Preserve both IDs for before/after comparison. Membership names the mount
    # through which this observer actually inspected the user/task inodes.
    return step, user, observer_mount, mount


def observe_current_cgroup(
    execution: SlurmExecutionIdentity,
    writer: ProcessIdentity,
    control: OperationControl,
) -> KernelCgroupObservation:
    """Keep the current-writer contract; foreign PIDs require the explicit API."""
    return _observe(execution, writer, control, current_only=True)


def observe_process_cgroup(
    execution: SlurmExecutionIdentity,
    writer: ProcessIdentity,
    control: OperationControl,
) -> KernelCgroupObservation:
    """Observe an explicitly known local process, never ownership or authority."""
    return _observe(execution, writer, control, current_only=False)


def _observe(
    execution: SlurmExecutionIdentity,
    writer: ProcessIdentity,
    control: OperationControl,
    *,
    current_only: bool,
) -> KernelCgroupObservation:
    execution = SlurmExecutionIdentity.model_validate(execution)
    writer = ProcessIdentity.model_validate(writer)
    readings = KernelReadings(control)
    try:
        control.checkpoint()
        if current_only and os.getpid() != writer.process_id:
            raise ValueError("Kernel observation requires this original Linux writer")
        if execution.job_id != execution.raw_job_id:
            raise ValueError("Array allocations are unsupported by this observer")
        before = _writer_snapshot(readings, execution, writer)
        step, user, mount, _ = before
        task = Path(user) / "task_0"
        identities = inspect_cgroup_chain(readings, task, mount)
        for path in (Path(user), task):
            if readings.read(path / "cgroup.type", 4096) != b"domain\n":
                raise ValueError("Threaded or unknown cgroup layout is unsupported")
            check_populated(readings.read(path / "cgroup.events", 4096))
        check_task_processes(
            readings.read(task / "cgroup.procs", 65536), writer.process_id
        )
        after = _writer_snapshot(readings, execution, writer)
        if before != after:
            raise ValueError("Writer cgroup or mount changed during observation")
        recheck_controls(readings)
        control.checkpoint()
        membership = SlurmCgroupMembership(
            job_id=execution.raw_job_id,
            step_id=step,
            writer=writer,
            uid=execution.uid,
            user_path=user,
            mount_id=mount.mount_id,
            device=identities[Path(user)].device,
            user_inode=identities[Path(user)].inode,
            task_inode=identities[task].inode,
        )
        return KernelCgroupObservation(membership, readings.capture())
    except BaseException as error:
        error.slurm_kernel_capture = readings.capture()  # type: ignore[attr-defined]
        raise
