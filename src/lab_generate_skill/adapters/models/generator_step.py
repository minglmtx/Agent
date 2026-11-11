"""Owned step observation/closure handle; cannot launch, signal or grant rights."""

from lab_generate_skill.adapters.processes.deadline import DeadlineControl

from dataclasses import dataclass
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from lab_generate_skill.domain.generator_step import (
    GeneratorStepStarted,
    GeneratorStepClosed,
)
from lab_generate_skill.domain.process_identity import (
    ProcessIdentity,
    ProcessTermination,
)
from lab_generate_skill.domain.slurm_allocation import SlurmAllocationObservation
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.adapters.slurm.step_launch import generator_step_name
from lab_generate_skill.adapters.slurm.kernel_capture import (
    KernelCapture,
    KernelReadings,
)
from lab_generate_skill.adapters.slurm.kernel_identity import read_process_identity
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    retained_capture,
)
from .generator_step_evidence import save_step_raw
from lab_generate_skill.adapters.slurm.gpu_step_observation import (
    observe_gpu_started,
    observe_gpu_closed,
)
from lab_generate_skill.adapters.slurm.cgroup_pin import PinnedUserTree


@dataclass
class GeneratorStepState:
    start_attempted: bool = False
    launcher: ProcessIdentity | None = None
    target: SlurmStepTarget | None = None
    started: GeneratorStepStarted | None = None


def same_allocation(
    expected: SlurmAllocationObservation, actual: SlurmAllocationObservation
) -> None:
    a, b = expected.facts, actual.facts
    if (a.execution, a.writer, a.controller, a.gpu, a.cgroup) != (
        b.execution,
        b.writer,
        b.controller,
        b.gpu,
        b.cgroup,
    ):
        raise OwnershipConflict("Generator allocation changed from its frozen original")


def retain_step_failure(
    store: EvidenceStore,
    state: GeneratorStepState,
    phase: str,
    kernels: list[KernelCapture],
    commands: list[CommandCapture],
    error: BaseException,
) -> None:
    pending = [error]
    while pending:
        failure = pending.pop(0)
        partial = getattr(failure, "slurm_kernel_capture", None)
        if isinstance(partial, KernelCapture) and not any(
            k is partial for k in kernels
        ):
            kernels.append(partial)
        for command in getattr(failure, "slurm_step_commands", ()):
            if not any(c is command for c in commands):
                commands.append(command)
        captured = retained_capture(failure)
        if captured is not None and not any(c is captured for c in commands):
            commands.append(captured)
        if isinstance(failure, BaseExceptionGroup):
            pending[0:0] = failure.exceptions
    if hasattr(error, "generator_step_evidence_ref"):
        return  # A raw publication may already have committed; do not replace it.
    try:
        ref = save_step_raw(
            store,
            state.target,
            phase,
            kernels,
            commands,
            error,
            control=DeadlineControl(5, "evidence-diagnostic"),
        )
    except BaseException as storage:
        group = BaseExceptionGroup(
            "Generator step observation and evidence failed", [error, storage]
        )
        if hasattr(storage, "generator_step_evidence_ref"):
            setattr(
                group,
                "generator_step_evidence_ref",
                getattr(storage, "generator_step_evidence_ref"),
            )
        raise group from None
    setattr(error, "generator_step_evidence_ref", ref)


def observe_started(
    spec: GeneratorResourceSpec,
    allocation: SlurmAllocationObservation,
    state: GeneratorStepState,
    worker: ProcessIdentity,
    evidence: EvidenceStore,
    control: OperationControl,
) -> GeneratorStepStarted:
    kernels: list[KernelCapture] = []
    commands: list[CommandCapture] = []
    try:
        observed = observe_gpu_started(
            allocation,
            state,
            worker,
            generator_step_name(spec.token),
            spec.slurm.scontrol_executable,
            kernels,
            commands,
            control,
        )
        ref = save_step_raw(
            evidence, state.target, "started", kernels, commands, control=control
        )
        state.started = GeneratorStepStarted(
            allocation=allocation, controller=observed, evidence=ref
        )
        control.checkpoint()
        return state.started
    except BaseException as error:
        retain_step_failure(evidence, state, "started", kernels, commands, error)
        raise


def observe_closed(
    spec: GeneratorResourceSpec,
    state: GeneratorStepState,
    termination: ProcessTermination,
    evidence: EvidenceStore,
    control: OperationControl,
    pinned: PinnedUserTree | None = None,
) -> GeneratorStepClosed | None:
    kernels: list[KernelCapture] = []
    commands: list[CommandCapture] = []
    try:
        closed = observe_gpu_closed(
            state,
            state.started.controller if state.started is not None else None,
            termination,
            spec.slurm.scontrol_executable,
            kernels,
            commands,
            control,
            pinned,
        )
        if closed is None:
            return None
        assert state.target is not None
        ref = save_step_raw(
            evidence, state.target, "closed", kernels, commands, control=control
        )
        result = GeneratorStepClosed(
            target=state.target, quiescence=closed, evidence=ref
        )
        control.checkpoint()
        return result
    except BaseException as error:
        retain_step_failure(evidence, state, "closed", kernels, commands, error)
        raise


def observe_launcher(pid: int, uid: int, control: OperationControl) -> ProcessIdentity:
    readings = KernelReadings(control)
    try:
        first = read_process_identity(readings, pid, uid)
        if read_process_identity(readings, pid, uid) != first:
            raise OwnershipConflict("Launcher incarnation changed during observation")
        return first
    except BaseException as error:
        setattr(error, "slurm_kernel_capture", readings.capture())
        raise
