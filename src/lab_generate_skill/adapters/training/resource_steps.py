"""Trainer role facts using the shared actual GPU-step observer and raw encoder."""

from dataclasses import dataclass
from lab_generate_skill.domain.training_resource import (
    TrainingResourceSpec,
    TrainingStepStarted,
    TrainingStepClosed,
)
from lab_generate_skill.domain.process_identity import (
    ProcessIdentity,
    ProcessTermination,
)
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from lab_generate_skill.domain.slurm_allocation import SlurmAllocationObservation
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    retained_capture,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.slurm.gpu_step_observation import (
    observe_gpu_started,
    observe_gpu_closed,
)
from lab_generate_skill.adapters.slurm.step_launch import training_step_name
from lab_generate_skill.adapters.slurm.step_evidence import encode_step_raw
from lab_generate_skill.adapters.slurm.kernel_capture import (
    KernelReadings,
    KernelCapture,
)
from lab_generate_skill.adapters.slurm.kernel_identity import read_process_identity
from lab_generate_skill.adapters.slurm.cgroup_pin import PinnedUserTree
from .resource_records import put_raw


@dataclass
class TrainingStepState:
    start_attempted: bool = False
    launcher: ProcessIdentity | None = None
    target: SlurmStepTarget | None = None
    started: TrainingStepStarted | None = None


def same_allocation(
    a: SlurmAllocationObservation, b: SlurmAllocationObservation
) -> None:
    if (
        a.facts.execution,
        a.facts.writer,
        a.facts.controller,
        a.facts.gpu,
        a.facts.cgroup,
    ) != (
        b.facts.execution,
        b.facts.writer,
        b.facts.controller,
        b.facts.gpu,
        b.facts.cgroup,
    ):
        raise OwnershipConflict("Original training allocation changed")


def launcher_identity(pid: int, uid: int, control: OperationControl) -> ProcessIdentity:
    readings = KernelReadings(control)
    try:
        first = read_process_identity(readings, pid, uid)
        if read_process_identity(readings, pid, uid) != first:
            raise OwnershipConflict("Training launcher incarnation changed")
        return first
    except BaseException as error:
        setattr(error, "slurm_kernel_capture", readings.capture())
        raise


def _failure(
    evidence: EvidenceStore,
    state: TrainingStepState,
    name: str,
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
        capture = retained_capture(failure)
        if capture is not None and not any(c is capture for c in commands):
            commands.append(capture)
        if isinstance(failure, BaseExceptionGroup):
            pending[0:0] = failure.exceptions
    raw = encode_step_raw(
        "sft-step-raw/1", state.target, name, kernels, commands, error
    )
    try:
        ref = put_raw(
            evidence, raw, "sft-step-raw/1", DeadlineControl(5, "sft-step-diagnostic")
        )
        setattr(error, "training_step_evidence_ref", ref)
    except BaseException as storage:
        raise BaseExceptionGroup(
            "Training step observation and raw evidence failed", [error, storage]
        ) from None


def observe_started(
    spec: TrainingResourceSpec,
    allocation: SlurmAllocationObservation,
    state: TrainingStepState,
    worker: ProcessIdentity,
    evidence: EvidenceStore,
    control: OperationControl,
) -> TrainingStepStarted:
    kernels: list[KernelCapture] = []
    commands: list[CommandCapture] = []
    try:
        observed = observe_gpu_started(
            allocation,
            state,
            worker,
            training_step_name(spec.configuration.token),
            spec.slurm.scontrol_executable,
            kernels,
            commands,
            control,
        )
        raw = encode_step_raw(
            "sft-step-raw/1", state.target, "started", kernels, commands, None
        )
        ref = put_raw(evidence, raw, "sft-step-raw/1", control)
        state.started = TrainingStepStarted(
            allocation=allocation, controller=observed, evidence=ref
        )
        return state.started
    except BaseException as error:
        _failure(evidence, state, "started", kernels, commands, error)
        raise


def observe_closed(
    spec: TrainingResourceSpec,
    state: TrainingStepState,
    termination: ProcessTermination,
    evidence: EvidenceStore,
    control: OperationControl,
    pinned: PinnedUserTree | None,
) -> TrainingStepClosed | None:
    kernels: list[KernelCapture] = []
    commands: list[CommandCapture] = []
    try:
        result = observe_gpu_closed(
            state,
            state.started.controller if state.started is not None else None,
            termination,
            spec.slurm.scontrol_executable,
            kernels,
            commands,
            control,
            pinned,
        )
        if result is None:
            return None
        assert state.target is not None
        raw = encode_step_raw(
            "sft-step-raw/1", state.target, "closed", kernels, commands, None
        )
        ref = put_raw(evidence, raw, "sft-step-raw/1", control)
        return TrainingStepClosed(target=state.target, quiescence=result, evidence=ref)
    except BaseException as error:
        _failure(evidence, state, "closed", kernels, commands, error)
        raise
