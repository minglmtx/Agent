"""Shared scalar original-batch binding; concrete providers own wire schemas."""

from pathlib import PurePosixPath
from typing import Self
from pydantic import Field, model_validator
from .validation import Contract
from .scheduler import SlurmExecutionIdentity
from .slurm_allocation import SlurmCgroupMembership


class ScalarBatchBinding(Contract):
    # Keep schema first so existing role canonical field order is unchanged.
    schema_version: str
    execution: SlurmExecutionIdentity
    parent: SlurmCgroupMembership
    srun_executable: str = Field(min_length=1, max_length=4096)
    scontrol_executable: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def original_batch(self) -> Self:
        if (
            self.execution.job_id != self.execution.raw_job_id
            or self.parent.job_id != self.execution.raw_job_id
            or self.parent.uid != self.execution.uid
            or self.parent.step_id != "batch"
        ):
            raise ValueError("Worker must retain its original scalar batch execution")
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
                    "Worker Slurm commands must be canonical absolute paths"
                )
        return self
