"""Original step target and readonly controller facts, never execution rights."""

from typing import Annotated, Literal, Self
from pydantic import Field, StringConstraints, model_validator

from .process_identity import ProcessIdentity
from .scheduler import SlurmExecutionIdentity
from .slurm_allocation import SlurmCgroupMembership
from .validation import Contract

StepName = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
]


class SlurmStepTarget(Contract):
    schema_version: Literal["slurm-step-target/2"] = "slurm-step-target/2"
    execution: SlurmExecutionIdentity
    step_name: StepName
    resources: Literal["single_gpu", "cpu_only"]
    launcher: ProcessIdentity
    worker: SlurmCgroupMembership

    @model_validator(mode="after")
    def original_numeric_step(self) -> Self:
        if (
            self.execution.job_id != self.execution.raw_job_id
            or self.worker.job_id != self.execution.raw_job_id
            or self.worker.uid != self.execution.uid
            or self.worker.step_id == "batch"
        ):
            raise ValueError(
                "Step target requires the original scalar execution and numeric worker step"
            )
        if (self.launcher.node_id, self.launcher.boot_id) != (
            self.worker.writer.node_id,
            self.worker.writer.boot_id,
        ) or self.launcher.process_id == self.worker.writer.process_id:
            raise ValueError(
                "Step launcher and worker must be distinct processes on the same host boot"
            )
        return self

    @property
    def step_key(self) -> str:
        return self.execution.raw_job_id + "." + self.worker.step_id


class SlurmControllerStep(Contract):
    schema_version: Literal["slurm-controller-step/2"] = "slurm-controller-step/2"
    target: SlurmStepTarget
    started_at_epoch: int = Field(gt=0)
    gpu_type: (
        Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
        | None
    )
    memory: Annotated[
        str, StringConstraints(pattern=r"^[1-9][0-9]{0,15}[KMGTPE]?$", max_length=17)
    ]

    @model_validator(mode="after")
    def step_after_allocation(self) -> Self:
        if (self.target.resources == "single_gpu") != (self.gpu_type is not None):
            raise ValueError(
                "Step GPU type must agree with its explicit resource profile"
            )
        if self.started_at_epoch < self.target.execution.started_at_epoch:
            raise ValueError("Step cannot start before the original allocation")
        return self
