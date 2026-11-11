"""Private, bounded task calls in an already acquired site worker.

These transport facts grant no task admission. Actual authority must verify
binding, payload sources, original instance, persistent intent and quiescence.
No field is a model prompt, executable script or whole-baseline receipt.
"""

import hashlib
from typing import Literal, Self
from pydantic import Field, field_validator, model_validator
from .validation import Contract
from .identity import TaskIdentity
from .evidence import EvidenceRef
from .lifecycle import OperationContext
from .state_scope import private_state_ref
from .site_worker import SiteWorkerConfiguration
from .errors import OwnershipConflict


class SiteTaskRequest(Contract):
    schema_version: Literal["site-task-request/2"] = "site-task-request/2"
    task: TaskIdentity
    binding_ref: EvidenceRef
    operation: OperationContext
    action: Literal["snapshot", "prepare", "inspect", "restore"]
    snapshot_ref: EvidenceRef | None = None
    private_input: str = Field(min_length=2, max_length=1048576)

    @field_validator("private_input")
    @classmethod
    def bounded(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 1048576:
            raise ValueError("Private task input exceeds byte limit")
        return value

    @model_validator(mode="after")
    def scope(self) -> Self:
        private_state_ref(self.binding_ref, "task-binding/1")
        op = self.operation
        if (
            op.mode != ("cleanup" if self.action == "restore" else "execute")
            or op.attempt_id is None
            or op.allocation_id is None
            or op.recovery_ref is None
        ):
            raise ValueError(
                "Task call needs explicit attempt, site allocation and task recovery"
            )
        private_state_ref(op.recovery_ref, "recovery-plan/1")
        if self.action == "snapshot":
            if self.snapshot_ref is not None:
                raise ValueError(
                    "Snapshot capture cannot replace an existing reference"
                )
        elif (
            self.snapshot_ref is None
            or self.snapshot_ref.visibility != "private"
            or self.snapshot_ref.media_type != "application/json"
        ):
            raise ValueError(
                "Task effects/reads/restore require original persisted private snapshot"
            )

        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    def check_site(self, configuration: SiteWorkerConfiguration) -> None:
        token, op = configuration.token, self.operation
        if (self.task.site, op.run_id, op.owner_id, op.allocation_id) != (
            configuration.site_id,
            token.owner.run_id,
            token.owner.owner_id,
            token.allocation_id,
        ):
            raise OwnershipConflict("Task call changed original owned site")


class SiteTaskResult(Contract):
    schema_version: Literal["site-task-result/1"] = "site-task-result/1"
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    private_result: str = Field(min_length=2, max_length=1048576)

    @field_validator("private_result")
    @classmethod
    def bounded(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 1048576:
            raise ValueError("Private task result exceeds byte limit")
        return value
