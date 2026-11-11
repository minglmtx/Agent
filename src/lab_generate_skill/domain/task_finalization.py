"""Frozen cleanup phases; original reset/resources remain separate contracts."""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract, Identifier
from .state_scope import StateScope, private_state_ref
from .lifecycle import AllocationToken, OperationContext
from .evidence import EvidenceRef


class TaskFinalizationPlan(Contract):
    schema_version: Literal["task-finalization-plan/1"] = "task-finalization-plan/1"
    scope: StateScope
    browser_close_operation_id: Identifier
    restore_operation_id: Identifier
    resume_operation_id: Identifier
    qualification_operation_id: Identifier
    reset_operation_id: Identifier

    @model_validator(mode="after")
    def original_stages(self) -> Self:
        ids = (
            self.browser_close_operation_id,
            self.restore_operation_id,
            self.resume_operation_id,
            self.qualification_operation_id,
            self.reset_operation_id,
        )
        if self.scope.task.split != "train" or len(set(ids)) != len(ids):
            raise ValueError(
                "Current train finalization requires distinct original phases"
            )
        if any(len(name) > 180 for name in ids):
            raise ValueError(
                "Cleanup identities must reserve room for original qualification reads"
            )
        return self


class UnstartedTaskBrowser(Contract):
    """Observed non-start premise; only independent actual authority can close it."""

    schema_version: Literal["unstarted-task-browser/2"] = "unstarted-task-browser/2"
    scope: StateScope
    token: AllocationToken
    operation: OperationContext
    reset_plan_ref: EvidenceRef
    preparation_declaration_ref: EvidenceRef
    finalization_declaration_ref: EvidenceRef
    owner_phase: Literal["not_constructed", "new"]
    registration: Literal["absent"] = "absent"

    @model_validator(mode="after")
    def original_scope(self) -> Self:
        private_state_ref(self.reset_plan_ref, "reset-plan/1")
        private_state_ref(
            self.preparation_declaration_ref, "site-task-preparation-plan/2"
        )
        private_state_ref(self.finalization_declaration_ref, "task-finalization-plan/1")
        if (
            self.token.owner,
            self.token.attempt_id,
            self.token.scope,
            self.token.resource_kind,
        ) != (self.scope.owner, self.scope.attempt_id, "attempt", "browser") or (
            self.operation.owner_id,
            self.operation.run_id,
            self.operation.attempt_id,
            self.operation.mode,
            self.operation.allocation_id,
            self.operation.recovery_ref,
        ) != (
            self.scope.owner.owner_id,
            self.scope.owner.run_id,
            self.scope.attempt_id,
            "cleanup",
            self.token.allocation_id,
            self.token.recovery_ref,
        ):
            raise ValueError(
                "Non-start observation changed original cleanup/resource scope"
            )
        return self
