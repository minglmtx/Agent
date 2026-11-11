"""Explicit post-restore frontend resume, not task reuse or recovery authority."""

import hashlib
from typing import Literal, Self
from pydantic import Field, field_validator, model_validator
from .validation import Contract, Sha256
from .site_task import SiteTaskRequest, SiteTaskResult
from .site_worker import SiteWorkerConfiguration
from .lifecycle import OperationContext
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .errors import OwnershipConflict


class SiteResumeRequest(Contract):
    schema_version: Literal["site-resume-request/1"] = "site-resume-request/1"
    restore_request: SiteTaskRequest
    restore_result_ref: EvidenceRef
    operation: OperationContext

    @model_validator(mode="after")
    def original_restore(self) -> Self:
        old, op = self.restore_request, self.operation
        private_state_ref(self.restore_result_ref, "site-task-result/1")
        if op.recovery_ref is None:
            raise ValueError("Resume requires explicit environment recovery")
        private_state_ref(op.recovery_ref, "recovery-plan/1")
        if (
            old.action != "restore"
            or op.mode != "cleanup"
            or op.parent_operation_id != old.operation.operation_id
        ):
            raise ValueError("Resume requires original completed restore parent")
        if (op.run_id, op.owner_id, op.attempt_id, op.allocation_id) != (
            old.operation.run_id,
            old.operation.owner_id,
            old.operation.attempt_id,
            old.operation.allocation_id,
        ) or op.operation_id == old.operation.operation_id:
            raise OwnershipConflict("Resume changed original task scope or operation")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    def check_site(self, configuration: SiteWorkerConfiguration) -> None:
        self.restore_request.check_site(configuration)
        if self.operation.recovery_ref != configuration.token.recovery_ref:
            raise OwnershipConflict("Resume changed original environment recovery")


class SiteResumeResult(Contract):
    schema_version: Literal["site-resume-result/1"] = "site-resume-result/1"
    request_sha256: Sha256
    private_result: str = Field(min_length=2, max_length=1048576)

    @field_validator("private_result")
    @classmethod
    def bounded(cls, value: str) -> str:
        return SiteTaskResult.bounded(value)


class SiteResumeIntent(Contract):
    schema_version: Literal["site-resume-intent/1"] = "site-resume-intent/1"
    configuration_sha256: Sha256
    request: SiteResumeRequest
