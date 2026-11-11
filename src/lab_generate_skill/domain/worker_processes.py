"""Shared exact CPU-domain guard facts; concrete roles own serialized schemas."""

from typing import Self
from pydantic import model_validator
from .validation import Contract
from .process_guard import ProcessOwnerGuard
from .slurm_step import SlurmStepTarget


class CpuProcessStopFacts(Contract):
    """Observed exact pidfd exits, not reaping or complete step-tree cleanliness."""

    schema_version: str
    target: SlurmStepTarget
    guard: ProcessOwnerGuard
    worker_signal_requested: bool = False
    supervisor_signal_requested: bool = False
    worker_exit_observed: bool = False
    supervisor_exit_observed: bool = False

    @model_validator(mode="after")
    def original_guard(self) -> Self:
        if (
            self.target.resources != "cpu_only"
            or self.target.worker.writer != self.guard.worker
            or self.target.launcher == self.guard.supervisor
        ):
            raise ValueError("Worker stop facts changed original CPU step and guard")
        return self
