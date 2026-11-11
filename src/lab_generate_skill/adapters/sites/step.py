"""Original CPU step observation and pinned closure; no launch or permission.

Accounting/release/site admission is mandatory in SiteResourceAuthority.
These observations independently bind the original local kernel/controller domain.
Partial state is retained before later reads/publications so cleanup never invents
another resource. Missing/foreign targets remain quarantined, never rediscovered.
"""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.site_resource import (
    SiteResourceReady,
    SiteStepClosed,
    SiteProcessStop,
)
from lab_generate_skill.domain.site_worker import SiteWorkerReady
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
from lab_generate_skill.adapters.slurm.step_launch import site_step_name
from lab_generate_skill.adapters.slurm.commands import SlurmCommandRunner
from lab_generate_skill.adapters.processes.capture import CommandCapture
from lab_generate_skill.adapters.slurm.worker_evidence import WorkerStepEvidence

_records = WorkerStepEvidence("site")
save, retain_failure = _records.save, _records.retain_failure
from lab_generate_skill.adapters.processes.worker_processes import (
    pin_worker_processes,
    PinnedWorkerProcesses,
)


@dataclass
class SiteStepState:
    launcher: ProcessIdentity | None = None
    target: SlurmStepTarget | None = None
    ready: SiteResourceReady | None = None
    pin: PinnedUserTree | None = None
    processes: PinnedWorkerProcesses[SiteProcessStop] | None = None


def check_parent(
    spec: SiteResourceSpec, controller: ProcessIdentity, control: OperationControl
) -> None:
    if controller != spec.slurm.parent.writer:
        raise OwnershipConflict("Site controller differs from original Slurm parent")
    observed = observe_process_cgroup(spec.slurm.execution, controller, control)
    if observed.membership != spec.slurm.parent:
        raise OwnershipConflict("Site parent changed its original batch cgroup")


def observe_launcher(
    spec: SiteResourceSpec, pid: int, control: OperationControl
) -> ProcessIdentity:
    return read_process_identity(KernelReadings(control), pid, spec.slurm.execution.uid)


def observe_ready(
    spec: SiteResourceSpec,
    state: SiteStepState,
    ready: SiteWorkerReady,
    evidence: EvidenceStore,
    control: OperationControl,
) -> SiteResourceReady:
    guard = ready.owner_guard
    kernels: list[KernelCapture] = []
    commands: list[CommandCapture] = []
    try:
        if (
            state.target is not None
            or state.pin is not None
            or state.ready is not None
            or state.processes is not None
        ):
            raise OwnershipConflict(
                "Site step was already observed; keep original handles"
            )
        if state.launcher is None or guard.controller != spec.slurm.parent.writer:
            raise OwnershipConflict("Site has no original launcher/controller")
        execution = spec.slurm.execution
        launcher = observe_process_cgroup(execution, state.launcher, control)
        kernels.append(launcher.capture)
        if (
            launcher.membership.step_id != "batch"
            or launcher.membership.user_inode != spec.slurm.parent.user_inode
            or launcher.membership.device != spec.slurm.parent.device
        ):
            raise OwnershipConflict("Site launcher left its original batch subtree")
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
                "Site supervisor and worker differ in original step"
            )
        state.target = SlurmStepTarget(
            execution=execution,
            step_name=site_step_name(spec.token),
            resources="cpu_only",
            launcher=state.launcher,
            worker=worker.membership,
        )
        state.pin = pin_user_tree(state.target.worker, control)
        kernels.append(state.pin.opened)
        state.processes = pin_worker_processes(
            SiteProcessStop(guard=guard, target=state.target), control
        )
        observed = SlurmStepObserver(
            SlurmCommandRunner(), scontrol=Path(spec.slurm.scontrol_executable)
        ).observe(state.target, control)
        commands.extend(observed.commands)
        assert observed.controller is not None
        repeated = observe_process_cgroup(execution, guard.worker, control)
        kernels.append(repeated.capture)
        if repeated.membership != worker.membership:
            raise OwnershipConflict(
                "Original site worker tree changed during acquisition"
            )
        reference = save(evidence, state.target, "ready", kernels, commands, control)
        state.ready = SiteResourceReady(
            worker=ready, controller=observed.controller, evidence=reference
        )
        control.checkpoint()
        return state.ready
    except BaseException as error:
        retain_failure(evidence, state.target, "ready", kernels, commands, error)
        raise


def observe_closed(
    spec: SiteResourceSpec,
    state: SiteStepState,
    termination: ProcessTermination | None,
    evidence: EvidenceStore,
    control: OperationControl,
    *,
    metadata_control: OperationControl,
) -> SiteStepClosed | None:
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
                "Original site step termination remains unconfirmed"
            )
        if state.pin is not None:
            if state.pin.original != state.target.worker:
                raise OwnershipConflict("Site cgroup pin changed original target")
            kernels.append(state.pin.opened)
        observer = SlurmStepObserver(
            SlurmCommandRunner(), scontrol=Path(spec.slurm.scontrol_executable)
        )
        absent = (
            observer.wait_absent(state.ready.controller, control)
            if state.ready is not None
            else observer.observe(state.target, control, require_absent=True)
        )
        commands.extend(absent.commands)
        closed = (
            state.pin.observe(control)
            if state.pin is not None
            else observe_user_quiescence(state.target.worker, control)
        )
        kernels.append(closed.capture)
        try:
            reference = save(
                evidence, state.target, "closed", kernels, commands, metadata_control
            )
        except BaseException as storage_error:
            # Retain the actual original observation independently of CAS
            # persistence. It is diagnostic data, never a closure grant.
            setattr(storage_error, "site_step_physical_target", state.target)
            setattr(storage_error, "site_step_physical_quiescence", closed.facts)
            raise
        return SiteStepClosed(
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
