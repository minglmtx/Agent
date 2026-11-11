"""Private failure diagnostics; never a complete or qualified native capture."""

import base64
from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.lifecycle import OperationContext
from ..project_copy import PROJECT_COPY


class GroupPartialCapture(Contract):
    schema_version: Literal["gitlab-group-partial-capture/1"] = (
        "gitlab-group-partial-capture/1"
    )
    request: SiteTaskRequest
    retention_operation: OperationContext
    failed_stage: Literal["groups", "projects", "envelope"]
    project_query: str = PROJECT_COPY
    group_reply_base64: str | None
    project_copy_base64: str | None
    qualified: Literal[False] = False

    @model_validator(mode="after")
    def original(self) -> Self:
        if self.project_query != PROJECT_COPY:
            raise ValueError("Partial diagnostic changed original project query")
        parent, child = self.request.operation, self.retention_operation
        if (
            child.mode != "cleanup"
            or child.parent_operation_id != parent.operation_id
            or child.cancellation_ref is not None
        ):
            raise ValueError(
                "Partial diagnostic requires independent original linked cleanup"
            )
        if (
            child.run_id,
            child.owner_id,
            child.attempt_id,
            child.allocation_id,
            child.recovery_ref,
        ) != (
            parent.run_id,
            parent.owner_id,
            parent.attempt_id,
            parent.allocation_id,
            parent.recovery_ref,
        ):
            raise ValueError("Partial diagnostic changed original request ownership")
        if self.failed_stage == "groups" and self.project_copy_base64 is not None:
            raise ValueError("Unexecuted project capture cannot have completed bytes")
        for value in (self.group_reply_base64, self.project_copy_base64):
            if (
                value is not None
                and base64.b64encode(base64.b64decode(value, validate=True)).decode()
                != value
            ):
                raise ValueError("Partial diagnostic changed native byte encoding")
        return self
