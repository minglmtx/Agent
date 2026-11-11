"""Frozen allocation and observed Actor step facts, separate from authority."""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from .evidence import EvidenceRef
from .slurm_allocation import SlurmAllocationObservation
from .slurm_step import SlurmControllerStep, SlurmStepTarget
from .slurm_quiescence import SlurmUserQuiescence, SlurmUserRemoval
from .validation import Contract
from .process_identity import ProcessIdentity


class ActorSlurmBinding(Contract):
    schema_version: Literal["actor-slurm-binding/1"] = "actor-slurm-binding/1"
    allocation: SlurmAllocationObservation
    srun_executable: str = Field(min_length=1, max_length=4096)
    scontrol_executable: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def fixed_parent_and_paths(self) -> Self:
        if self.allocation.facts.cgroup.step_id != "batch":
            raise ValueError("Actor parent must belong to the original batch step")
        for value in (self.srun_executable, self.scontrol_executable):
            path = PurePosixPath(value)
            if (
                not path.is_absolute()
                or str(path) != value
                or ".." in path.parts
                or "\\" in value
                or any(ord(x) < 32 for x in value)
            ):
                raise ValueError(
                    "Actor Slurm executables must be canonical absolute paths"
                )
        return self


class ActorStepStarted(Contract):
    schema_version: Literal["actor-step-started/1"] = "actor-step-started/1"
    allocation: SlurmAllocationObservation
    controller: SlurmControllerStep
    evidence: EvidenceRef

    @model_validator(mode="after")
    def original_allocation(self) -> Self:
        target, facts = self.controller.target, self.allocation.facts
        if (
            target.resources != "single_gpu"
            or target.execution != facts.execution
            or target.launcher.node_id != facts.writer.node_id
            or target.launcher.boot_id != facts.writer.boot_id
            or self.controller.gpu_type != facts.controller.gpu_type
        ):
            raise ValueError(
                "Started step differs from original allocation/physical GPU type"
            )
        _raw(self.evidence)
        return self


class ActorStepClosed(Contract):
    schema_version: Literal["actor-step-closed/1"] = "actor-step-closed/1"
    target: SlurmStepTarget
    quiescence: SlurmUserQuiescence | SlurmUserRemoval
    evidence: EvidenceRef

    @model_validator(mode="after")
    def original_tree(self) -> Self:
        if self.quiescence.original != self.target.worker:
            raise ValueError("Closure belongs to a different original step tree")
        _raw(self.evidence)
        return self


class ActorStepCleanup(Contract):
    """Original owned-handle facts, not a claim that physical cleanup succeeded."""

    schema_version: Literal["actor-step-cleanup/1"] = "actor-step-cleanup/1"
    start_attempted: bool
    launcher: ProcessIdentity | None = None
    target: SlurmStepTarget | None = None
    started: ActorStepStarted | None = None

    @model_validator(mode="after")
    def original_handle(self) -> Self:
        if not self.start_attempted and any(
            x is not None for x in (self.launcher, self.target, self.started)
        ):
            raise ValueError("Unattempted start cannot contain process or step facts")
        if self.target is not None and self.target.launcher != self.launcher:
            raise ValueError("Cleanup target differs from original launcher")
        if self.started is not None and self.started.controller.target != self.target:
            raise ValueError("Cleanup acquisition differs from original target")
        return self


def _raw(reference: EvidenceRef) -> None:
    if (reference.visibility, reference.content_schema) != (
        "private",
        "actor-step-raw/1",
    ):
        raise ValueError("Actor step facts require private raw evidence")
