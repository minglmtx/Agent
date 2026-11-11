"""Original CPU step observation and pinned closure; no launch or permission.

Accounting/release/site admission is mandatory in BrowserResourceAuthority.
These observations independently bind the original local kernel/controller domain.
Partial state is retained before later reads/publications so cleanup never invents
another resource. Missing/foreign targets remain quarantined, never rediscovered.
"""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.browser_step import BrowserStepStarted, BrowserStepClosed
from lab_generate_skill.domain.process_identity import (
    ProcessIdentity,
    ProcessTermination,
)
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.slurm.kernel_capture import (
    KernelReadings,
    KernelCapture,
)
from lab_generate_skill.adapters.slurm.kernel_identity import read_process_identity
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.adapters.slurm.cgroup_pin import pin_user_tree, PinnedUserTree
from lab_generate_skill.adapters.slurm.cgroup_quiescence import observe_user_quiescence
from lab_generate_skill.adapters.slurm.step import SlurmStepObserver
from lab_generate_skill.adapters.slurm.step_launch import browser_step_name
from lab_generate_skill.adapters.slurm.commands import SlurmCommandRunner
from lab_generate_skill.adapters.processes.capture import CommandCapture
from .step_records import save, retain_failure
from .step_processes import pin_browser_processes, PinnedBrowserProcesses


@dataclass
class BrowserStepState:
    launcher: ProcessIdentity | None = None
    target: SlurmStepTarget | None = None
    started: BrowserStepStarted | None = None
    pin: PinnedUserTree | None = None
    processes: PinnedBrowserProcesses | None = None


def check_parent(
    spec: BrowserResourceSpec, controller: ProcessIdentity, control: OperationControl
) -> None:
    if controller != spec.slurm.parent.writer:
        raise OwnershipConflict("Browser controller differs from original Slurm parent")
    observed = observe_process_cgroup(spec.slurm.execution, controller, control)
    if observed.membership != spec.slurm.parent:
        raise OwnershipConflict("Browser parent changed its original batch cgroup")


def observe_launcher(
    spec: BrowserResourceSpec, pid: int, control: OperationControl
) -> ProcessIdentity:
    return read_process_identity(KernelReadings(control), pid, spec.slurm.execution.uid)


def observe_started(
    spec: BrowserResourceSpec,
    state: BrowserStepState,
    guard: ProcessOwnerGuard,
    evidence: EvidenceStore,
    control: OperationControl,
) -> BrowserStepStarted:
    kernels: list[KernelCapture] = []
    commands: list[CommandCapture] = []
    try:
        if (
            state.target is not None
            or state.pin is not None
            or state.started is not None
            or state.processes is not None
        ):
            raise OwnershipConflict(
                "Browser step was already observed; keep original handles"
            )
        if state.launcher is None or guard.controller != spec.slurm.parent.writer:
            raise OwnershipConflict("Browser has no original launcher/controller")
        execution = spec.slurm.execution
        launcher = observe_process_cgroup(execution, state.launcher, control)
        kernels.append(launcher.capture)
        if (
            launcher.membership.step_id != "batch"
            or launcher.membership.user_inode != spec.slurm.parent.user_inode
            or launcher.membership.device != spec.slurm.parent.device
        ):
            raise OwnershipConflict("Browser launcher left its original batch subtree")
        worker = observe_process_cgroup(execution, guard.worker, control)
        kernels.append(worker.capture)
        supervisor = observe_process_cgroup(execution, guard.supervisor, control)
        kernels.append(supervisor.capture)
        if (
            supervisor.membership.step_id,
            supervisor.membership.user_inode,
            supervisor.membership.device,
        ) != (
            worker.membership.step_id,
            worker.membership.user_inode,
            worker.membership.device,
        ):
            raise OwnershipConflict(
                "Browser supervisor and worker differ in original step"
            )
        state.target = SlurmStepTarget(
            execution=execution,
            step_name=browser_step_name(spec.token),
            resources="cpu_only",
            launcher=state.launcher,
            worker=worker.membership,
        )
        state.pin = pin_user_tree(state.target.worker, control)
        kernels.append(state.pin.opened)
        state.processes = pin_browser_processes(guard, state.target, control)
        observed = SlurmStepObserver(
            SlurmCommandRunner(), scontrol=Path(spec.slurm.scontrol_executable)
        ).observe(state.target, control)
        commands.extend(observed.commands)
        assert observed.controller is not None
        repeated = observe_process_cgroup(execution, guard.worker, control)
        kernels.append(repeated.capture)
        if repeated.membership != worker.membership:
            raise OwnershipConflict(
                "Original browser worker tree changed during acquisition"
            )
        reference = save(evidence, state.target, "started", kernels, commands, control)
        state.started = BrowserStepStarted(
            controller=observed.controller, evidence=reference
        )
        control.checkpoint()
        return state.started
    except BaseException as error:
        retain_failure(evidence, state.target, "started", kernels, commands, error)
        raise


def observe_closed(
    spec: BrowserResourceSpec,
    state: BrowserStepState,
    termination: ProcessTermination | None,
    evidence: EvidenceStore,
    control: OperationControl,
    *,
    metadata_control: OperationControl | None = None,
) -> BrowserStepClosed | None:
    metadata_control = control if metadata_control is None else metadata_control
    kernels: list[KernelCapture] = []
    commands: list[CommandCapture] = []
    try:
        if (
            termination is not None
            and termination.state == "not_started"
            and termination.process_id is None
            and state.launcher is None
            and state.target is None
        ):
            return None
        if (
            state.target is None
            or state.launcher is None
            or termination is None
            or termination.state != "reaped"
            or termination.cleanup_errors
            or termination.process_id != state.launcher.process_id
        ):
            raise OwnershipConflict(
                "Original browser step termination remains unconfirmed"
            )
        if state.pin is not None:
            if state.pin.original != state.target.worker:
                raise OwnershipConflict("Browser cgroup pin changed original target")
            kernels.append(state.pin.opened)
        observer = SlurmStepObserver(
            SlurmCommandRunner(), scontrol=Path(spec.slurm.scontrol_executable)
        )
        absent = (
            observer.wait_absent(state.started.controller, control)
            if state.started is not None
            else observer.observe(state.target, control, require_absent=True)
        )
        commands.extend(absent.commands)
        closed = (
            state.pin.observe(control)
            if state.pin is not None
            else observe_user_quiescence(state.target.worker, control)
        )
        kernels.append(closed.capture)
        reference = save(
            evidence, state.target, "closed", kernels, commands, metadata_control
        )
        return BrowserStepClosed(
            target=state.target, quiescence=closed.facts, evidence=reference
        )
    except BaseException as error:
        retain_failure(
            evidence,
            state.target,
            "closed",
            kernels,
            commands,
            error,
            metadata_control=metadata_control,
        )
        raise
