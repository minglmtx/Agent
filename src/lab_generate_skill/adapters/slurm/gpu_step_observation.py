"""Shared actual GPU-step observation; role wrappers publish their own facts.

No process launch, signalling, restoration or execution authority lives here.
"""

from pathlib import Path
from typing import Protocol
from lab_generate_skill.domain.process_identity import (
    ProcessIdentity,
    ProcessTermination,
)
from lab_generate_skill.domain.slurm_allocation import SlurmAllocationObservation
from lab_generate_skill.domain.slurm_step import SlurmStepTarget, SlurmControllerStep
from lab_generate_skill.domain.slurm_quiescence import (
    SlurmUserQuiescence,
    SlurmUserRemoval,
)
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.capture import CommandCapture
from .kernel_capture import KernelCapture, KernelReadings
from .kernel_identity import read_process_identity
from .linux_cgroups import observe_process_cgroup
from .cgroup_quiescence import observe_user_quiescence
from .cgroup_pin import PinnedUserTree
from .commands import SlurmCommandRunner
from .step import SlurmStepObserver


class GpuStepHandles(Protocol):
    start_attempted: bool
    launcher: ProcessIdentity | None
    target: SlurmStepTarget | None


def observe_gpu_started(
    allocation: SlurmAllocationObservation,
    state: GpuStepHandles,
    worker: ProcessIdentity,
    step_name: str,
    scontrol: str,
    kernels: list[KernelCapture],
    commands: list[CommandCapture],
    control: OperationControl,
) -> SlurmControllerStep:
    if state.launcher is None:
        raise OwnershipConflict("Original step launcher identity is unknown")
    execution = allocation.facts.execution
    launcher = observe_process_cgroup(execution, state.launcher, control)
    kernels.append(launcher.capture)
    if (
        launcher.membership.step_id != "batch"
        or launcher.membership.user_inode != allocation.facts.cgroup.user_inode
    ):
        raise OwnershipConflict("Step launcher is outside the original parent subtree")
    try:
        live = observe_process_cgroup(execution, worker, control)
    except ValueError as mismatch:
        error = EvidenceIntegrityError(
            "Worker handshake differs from its original kernel identity"
        )
        partial = getattr(mismatch, "slurm_kernel_capture", None)
        if isinstance(partial, KernelCapture):
            setattr(error, "slurm_kernel_capture", partial)
        raise error from mismatch
    kernels.append(live.capture)
    state.target = SlurmStepTarget(
        resources="single_gpu",
        execution=execution,
        step_name=step_name,
        launcher=state.launcher,
        worker=live.membership,
    )
    observed = SlurmStepObserver(SlurmCommandRunner(), scontrol=Path(scontrol)).observe(
        state.target, control
    )
    commands.extend(observed.commands)
    assert observed.controller is not None
    repeated = observe_process_cgroup(execution, worker, control)
    kernels.append(repeated.capture)
    if repeated.membership != live.membership:
        raise OwnershipConflict("Original worker tree changed during acquisition")
    return observed.controller


def observe_gpu_closed(
    state: GpuStepHandles,
    started: SlurmControllerStep | None,
    termination: ProcessTermination,
    scontrol: str,
    kernels: list[KernelCapture],
    commands: list[CommandCapture],
    control: OperationControl,
    pinned: PinnedUserTree | None = None,
) -> SlurmUserQuiescence | SlurmUserRemoval | None:
    if not state.start_attempted and termination.state == "not_started":
        return None
    if state.target is None or state.launcher is None:
        raise OwnershipConflict(
            "Attempted step has no verified original identity; retain quarantine"
        )
    if (
        termination.state != "reaped"
        or termination.process_id != state.launcher.process_id
        or termination.cleanup_errors
    ):
        raise OwnershipConflict("Original launcher termination is unconfirmed")
    if pinned is not None:
        if pinned.original != state.target.worker:
            raise OwnershipConflict("Pinned tree differs from original target")
        kernels.append(pinned.opened)
    closed = (
        observe_user_quiescence(state.target.worker, control)
        if pinned is None
        else pinned.observe(control)
    )
    kernels.append(closed.capture)
    observer = SlurmStepObserver(SlurmCommandRunner(), scontrol=Path(scontrol))
    absent = (
        observer.observe(state.target, control, require_absent=True)
        if started is None
        else observer.wait_absent(started, control)
    )
    commands.extend(absent.commands)
    return closed.facts
