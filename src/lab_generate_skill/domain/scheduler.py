"""Exact scheduler observations, never writer takeover or retry permission.

An execution is bound before effects by the submitting/worker registration flow.
Job IDs alone may be reused/requeued. These observations describe accounting and
queue facts only: process containment, descendants and admission fencing belong
to the independent termination authority.
"""

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from .evidence import EvidenceRef
from .validation import Contract

SlurmJobId = Annotated[
    str, StringConstraints(pattern=r"^[1-9][0-9]{0,19}(?:_[0-9]{1,20})?$")
]
SlurmNumber = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,19}$")]
SlurmState = Annotated[
    str, StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Z_]+$")
]


class SlurmExecutionIdentity(Contract):
    schema_version: Literal["slurm-execution/1"] = "slurm-execution/1"
    cluster: Annotated[
        str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    ]
    job_id: SlurmJobId
    raw_job_id: SlurmNumber
    database_index: SlurmNumber
    uid: int = Field(ge=0, le=4294967294)
    submitted_at_epoch: int = Field(gt=0, le=253402300799)
    started_at_epoch: int = Field(gt=0, le=253402300799)
    restart_count: int = Field(ge=0, le=4294967295)

    @model_validator(mode="after")
    def exact_started_execution(self) -> Self:
        if "_" not in self.job_id and self.job_id != self.raw_job_id:
            raise ValueError("Scalar job must match its raw allocation ID")
        if self.started_at_epoch < self.submitted_at_epoch:
            raise ValueError("Start cannot precede submission")
        return self


class SlurmJobObservation(Contract):
    schema_version: Literal["slurm-job-observation/1"] = "slurm-job-observation/1"
    execution: SlurmExecutionIdentity
    observed_at: AwareDatetime
    accounting_state: SlurmState
    ended_at_epoch: int | None = Field(default=None, gt=0, le=253402300799)
    exit_status: int = Field(ge=0, le=255)
    exit_signal: int = Field(ge=0, le=255)
    queue_state: SlurmState | None
    evidence: EvidenceRef

    @model_validator(mode="after")
    def retained_facts(self) -> Self:
        if self.ended_at_epoch is not None and (
            self.ended_at_epoch < self.execution.started_at_epoch
        ):
            raise ValueError("End cannot precede the bound start")
        if (
            self.evidence.visibility != "private"
            or self.evidence.content_schema != "slurm-probe/1"
        ):
            raise ValueError("Scheduler facts require private versioned raw evidence")
        return self


class SchedulerProbeError(RuntimeError):
    """Read failed/ambiguous; preserve diagnostic evidence, never infer absence."""

    def __init__(self, reason: str, evidence: EvidenceRef) -> None:
        self.reason_code = reason
        self.evidence = evidence
        super().__init__(f"Scheduler observation rejected: {reason}")
