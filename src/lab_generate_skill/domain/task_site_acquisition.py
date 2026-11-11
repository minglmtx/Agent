"""Actual original acquisition facts, never a precomputed startup or dispatch permit."""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract
from .state_scope import StateScope, private_state_ref
from .lifecycle import OperationContext
from .evidence import EvidenceRef


class SiteTaskAcquired(Contract):
    schema_version: Literal["site-task-acquired/1"] = "site-task-acquired/1"
    scope: StateScope
    declaration_ref: EvidenceRef
    operation: OperationContext
    site_started_ref: EvidenceRef
    resource_intent_ref: EvidenceRef
    resource_acquired_ref: EvidenceRef

    @model_validator(mode="after")
    def actual(self) -> Self:
        for ref, schema in (
            (self.declaration_ref, "site-task-preparation-plan/2"),
            (self.site_started_ref, "site-resource-started/1"),
            (self.resource_intent_ref, "resource-acquisition-intent/1"),
            (self.resource_acquired_ref, "site-resource-fact/1"),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json" or ref.size_bytes == 0:
                raise ValueError("Original complete nonempty acquisition JSON required")
        op, scope = self.operation, self.scope
        if scope.task.split != "train" or (
            op.run_id,
            op.owner_id,
            op.attempt_id,
            op.mode,
            op.allocation_id,
            op.recovery_ref,
        ) != (
            scope.owner.run_id,
            scope.owner.owner_id,
            scope.attempt_id,
            "execute",
            None,
            None,
        ):
            raise ValueError("Acquired binding requires original task acquiring scope")
        return self
