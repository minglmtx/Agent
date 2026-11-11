"""One original SFT allocation/dispatch and real step facts; never grants rights."""

import hashlib
from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract
from .training_worker import TrainingWorkerConfiguration
from .training_worker_call import TrainingWorkerCommand
from .slurm_allocation import SlurmAllocationObservation
from .slurm_step import SlurmControllerStep, SlurmStepTarget
from .slurm_quiescence import SlurmUserQuiescence, SlurmUserRemoval
from .process_guard import ProcessOwnerGuard
from .process_identity import ProcessTermination, ProcessIdentity
from .release_installation import InstalledReleaseSources
from .lifecycle import OperationContext
from .evidence import EvidenceRef
from .state_scope import private_state_ref


class TrainingSlurmBinding(Contract):
    schema_version: Literal["sft-slurm-binding/1"] = "sft-slurm-binding/1"
    allocation: SlurmAllocationObservation
    srun_executable: str
    scontrol_executable: str

    @model_validator(mode="after")
    def original_batch(self) -> Self:
        if self.allocation.facts.cgroup.step_id != "batch":
            raise ValueError("Training controller must be in its original batch step")
        for value in (self.srun_executable, self.scontrol_executable):
            path = PurePosixPath(value)
            if (
                not path.is_absolute()
                or str(path) != value
                or ".." in path.parts
                or len(value) > 4096
                or any(ord(c) < 32 or c == "\\" for c in value)
            ):
                raise ValueError("Canonical fixed Slurm executable paths required")
        return self


class TrainingResourceSpec(Contract):
    schema_version: Literal["sft-resource-spec/1"] = "sft-resource-spec/1"
    configuration: TrainingWorkerConfiguration
    slurm: TrainingSlurmBinding
    operation: OperationContext

    @model_validator(mode="after")
    def original_resource_scope(self) -> Self:
        c, op = self.configuration, self.operation
        token, original = c.token, c.output.training.dataset.operation
        if op.mode != "execute" or (
            op.run_id,
            op.owner_id,
            op.allocation_id,
            op.attempt_id,
            op.recovery_ref,
        ) != (
            token.owner.run_id,
            token.owner.owner_id,
            token.allocation_id,
            token.attempt_id,
            token.recovery_ref,
        ):
            raise ValueError(
                "Training acquire must address its exact original allocation"
            )
        if (
            op.deadline > original.deadline
            or op.cancellation_ref != original.cancellation_ref
        ):
            raise ValueError(
                "Training resource cannot renew original execution deadline/cancellation"
            )
        a = self.slurm.allocation.facts
        if (
            token.owner.job_id != a.execution.job_id
            or token.owner.job_id != a.execution.raw_job_id
        ):
            raise ValueError("Training resource must use its original actual Slurm job")
        if len(self.model_dump_json().encode()) > 15 * 1024**2:
            raise ValueError("Training resource specification exceeds metadata bound")
        return self


class TrainingLaunch(Contract):
    schema_version: Literal["sft-training-launch/1"] = "sft-training-launch/1"
    spec: TrainingResourceSpec
    train: TrainingWorkerCommand
    command_ref: EvidenceRef

    @model_validator(mode="after")
    def exact_original_wire(self) -> Self:
        private_state_ref(self.command_ref, "sft-worker-command/1")
        raw = self.train.model_dump_json().encode()
        if (
            self.train.operation != "train"
            or self.train.sequence != 2
            or self.train.session_id
            != self.spec.configuration.token.expected_resource_id
            or (self.command_ref.sha256, self.command_ref.size_bytes)
            != (hashlib.sha256(raw).hexdigest(), len(raw))
        ):
            raise ValueError(
                "Acquisition must bind exact original once-only train bytes"
            )
        if len(self.model_dump_json().encode()) > 16 * 1024**2:
            raise ValueError("Complete training launch exceeds metadata bound")
        return self


class TrainingStepStarted(Contract):
    schema_version: Literal["sft-step-started/1"] = "sft-step-started/1"
    allocation: SlurmAllocationObservation
    controller: SlurmControllerStep
    evidence: EvidenceRef

    @model_validator(mode="after")
    def original_allocation(self) -> Self:
        t, a = self.controller.target, self.allocation.facts
        if (
            t.resources != "single_gpu"
            or t.execution != a.execution
            or (t.launcher.node_id, t.launcher.boot_id)
            != (a.writer.node_id, a.writer.boot_id)
            or self.controller.gpu_type != a.controller.gpu_type
        ):
            raise ValueError("Training step changed original allocation/GPU")
        private_state_ref(self.evidence, "sft-step-raw/1")
        return self


class TrainingStepClosed(Contract):
    schema_version: Literal["sft-step-closed/1"] = "sft-step-closed/1"
    target: SlurmStepTarget
    quiescence: SlurmUserQuiescence | SlurmUserRemoval
    evidence: EvidenceRef

    @model_validator(mode="after")
    def original_tree(self) -> Self:
        if self.quiescence.original != self.target.worker:
            raise ValueError("Training closure changed original worker subtree")
        private_state_ref(self.evidence, "sft-step-raw/1")
        return self


class TrainingResourceAcquired(Contract):
    schema_version: Literal["sft-resource-acquired/1"] = "sft-resource-acquired/1"
    launch_ref: EvidenceRef
    guard: ProcessOwnerGuard
    installed: InstalledReleaseSources
    step: TrainingStepStarted
    configure_command_ref: EvidenceRef
    configure_reply_ref: EvidenceRef

    @model_validator(mode="after")
    def actual_worker(self) -> Self:
        for ref, schema in (
            (self.launch_ref, "sft-training-launch/1"),
            (self.configure_command_ref, "sft-worker-command/1"),
            (self.configure_reply_ref, "sft-worker-reply/1"),
        ):
            private_state_ref(ref, schema)
        if self.guard.worker != self.step.controller.target.worker.writer:
            raise ValueError("Training acquisition changed actual worker identity")
        return self


class TrainingStepCleanup(Contract):
    schema_version: Literal["sft-step-cleanup/1"] = "sft-step-cleanup/1"
    start_attempted: bool
    launcher: ProcessIdentity | None
    target: SlurmStepTarget | None
    started: TrainingStepStarted | None

    @model_validator(mode="after")
    def original_handle(self) -> Self:
        if not self.start_attempted and any(
            v is not None for v in (self.launcher, self.target, self.started)
        ):
            raise ValueError("Unattempted training start cannot claim observed handles")
        if self.target is not None and self.target.launcher != self.launcher:
            raise ValueError("Training target changed original launcher")
        if self.started is not None and self.started.controller.target != self.target:
            raise ValueError("Training cleanup changed acquired target")
        return self


class TrainingResourceClosed(Contract):
    schema_version: Literal["sft-resource-closed/1"] = "sft-resource-closed/1"
    launch_ref: EvidenceRef
    acquired_ref: EvidenceRef | None
    execution_ref: EvidenceRef | None
    reply_ref: EvidenceRef | None
    step: TrainingStepClosed | None
    operation: OperationContext
    status: Literal["closed", "quarantined"]
    start_attempted: bool
    launcher: ProcessIdentity | None
    termination: ProcessTermination
    primary_error: str | None
    cleanup_errors: tuple[str, ...]

    @model_validator(mode="after")
    def original_complete_close(self) -> Self:
        for ref, schema in (
            (self.launch_ref, "sft-training-launch/1"),
            (self.acquired_ref, "sft-resource-acquired/1"),
            (self.execution_ref, "sft-native-execution/1"),
            (self.reply_ref, "sft-worker-reply/1"),
        ):
            if ref is not None:
                private_state_ref(ref, schema)
        if self.operation.mode != "cleanup":
            raise ValueError("Training close uses its original bounded cleanup scope")
        if self.status == "closed":
            if self.cleanup_errors or self.termination.cleanup_errors:
                raise ValueError("Training closed cannot hide cleanup errors")
            if self.start_attempted:
                if (
                    self.step is None
                    or self.launcher is None
                    or self.termination.state != "reaped"
                    or self.termination.process_id != self.launcher.process_id
                    or self.step.target.launcher != self.launcher
                ):
                    raise ValueError(
                        "Started training requires actual original full step closure"
                    )
            elif (
                self.termination.state != "not_started"
                or self.launcher is not None
                or self.step is not None
            ):
                raise ValueError(
                    "Unstarted training cannot invent process/step closure"
                )
        return self
