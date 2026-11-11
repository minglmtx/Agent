"""Pure frozen preparation; actual acquired site facts are published separately."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract, NonEmptyText
from .state_scope import StateScope, private_state_ref
from .evidence import EvidenceRef
from .lifecycle import OperationContext
from .preparation_record import PreparedPublication


class SiteTaskPreparationPlan(Contract):
    schema_version: Literal["site-task-preparation-plan/2"] = (
        "site-task-preparation-plan/2"
    )
    scope: StateScope
    site_spec_ref: EvidenceRef
    task_binding_ref: EvidenceRef
    private_input_ref: EvidenceRef
    snapshot_schema: NonEmptyText = Field(max_length=128)
    snapshot_operation: OperationContext
    prepare_operation: OperationContext
    environment_operation: OperationContext
    resource_read_operation: OperationContext

    @model_validator(mode="after")
    def original(self) -> Self:
        for ref, schema in (
            (self.site_spec_ref, "site-resource-spec/1"),
            (self.task_binding_ref, "task-binding/1"),
        ):
            private_state_ref(ref, schema)
        if (
            self.private_input_ref.visibility != "private"
            or self.private_input_ref.media_type != "application/json"
        ):
            raise ValueError("Original complete private task JSON required")
        scope = self.scope
        if scope.task.split != "train":
            raise ValueError("Construction preparation is train-only")
        operations = (
            self.snapshot_operation,
            self.prepare_operation,
            self.environment_operation,
        )
        if (
            len({op.operation_id for op in (*operations, self.resource_read_operation)})
            != 4
        ):
            raise ValueError(
                "Each original preparation phase needs a distinct operation"
            )
        if any(
            (op.run_id, op.owner_id, op.attempt_id, op.mode)
            != (scope.owner.run_id, scope.owner.owner_id, scope.attempt_id, "execute")
            or op.allocation_id is None
            or op.recovery_ref is None
            for op in operations
        ):
            raise ValueError("Preparation phases need original attempt/resource scopes")
        if (
            self.snapshot_operation.allocation_id,
            self.snapshot_operation.recovery_ref,
        ) != (
            self.prepare_operation.allocation_id,
            self.prepare_operation.recovery_ref,
        ) or self.environment_operation.allocation_id != self.prepare_operation.allocation_id:
            raise ValueError("Preparation phases changed original site/task recovery")
        read = self.resource_read_operation
        if (
            read.run_id,
            read.owner_id,
            read.attempt_id,
            read.mode,
            read.allocation_id,
            read.recovery_ref,
        ) != (
            scope.owner.run_id,
            scope.owner.owner_id,
            None,
            "cleanup",
            self.environment_operation.allocation_id,
            self.environment_operation.recovery_ref,
        ):
            raise ValueError(
                "Held batch site requires independent original resource read"
            )
        return self


class SiteTaskPrepared(Contract):
    schema_version: Literal["site-task-prepared/2"] = "site-task-prepared/2"
    scope: StateScope
    declaration_ref: EvidenceRef
    acquired_ref: EvidenceRef
    snapshot_request_ref: EvidenceRef
    snapshot_result_ref: EvidenceRef
    snapshot_ref: EvidenceRef
    environment_selection_ref: EvidenceRef
    environment_ref: EvidenceRef
    publication: PreparedPublication

    @model_validator(mode="after")
    def references(self) -> Self:
        for ref, schema in (
            (self.declaration_ref, "site-task-preparation-plan/2"),
            (self.acquired_ref, "site-task-acquired/1"),
            (self.snapshot_request_ref, "site-task-request/2"),
            (self.snapshot_result_ref, "site-task-result/1"),
            (self.environment_selection_ref, "environment-selection/1"),
            (self.environment_ref, "environment-baseline/1"),
        ):
            private_state_ref(ref, schema)
        if (
            self.snapshot_ref.visibility != "private"
            or self.snapshot_ref.media_type != "application/json"
        ):
            raise ValueError("Original private snapshot required")
        if self.publication.selection.environment_ref != self.environment_ref:
            raise ValueError("Prepared result changed original environment")
        return self
