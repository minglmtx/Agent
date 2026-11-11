"""Verified controller time fields, not a launch or recovery permission."""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .scheduler import SlurmExecutionIdentity
from .slurm_allocation import NodeName
from .validation import Contract


class SlurmJobTimeLimit(Contract):
    schema_version: Literal["slurm-job-time-limit/1"] = "slurm-job-time-limit/1"
    execution: SlurmExecutionIdentity
    node_id: NodeName
    observed_at: AwareDatetime
    controller_end: AwareDatetime
    hard_end: AwareDatetime
    time_limit_minutes: int = Field(gt=0, le=525600)

    @model_validator(mode="after")
    def finite_running_interval(self) -> Self:
        started = self.execution.started_at_epoch
        if not started <= self.observed_at.timestamp() < self.hard_end.timestamp():
            raise ValueError("Controller time limit must cover the running observation")
        if self.hard_end.timestamp() != min(
            self.controller_end.timestamp(), started + self.time_limit_minutes * 60
        ):
            raise ValueError(
                "Hard end must be the earlier finite controller/configured limit"
            )
        return self
