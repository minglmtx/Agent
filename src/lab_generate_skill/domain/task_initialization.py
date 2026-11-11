"""Frozen current initial measurement and Actor settings, without resource rights."""

from typing import Literal, Self, Any
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .validation import Contract, Identifier
from .actor_execution_window import ActorGenerationBudgets
from .lifecycle import AllocationToken, OperationContext
from .state_scope import StateScope, private_state_ref
from .evidence import EvidenceRef
from .optional_policies import InactivePolicy


class TaskActorInitialization(Contract):
    schema_version: Literal["task-actor-initialization/1"] = (
        "task-actor-initialization/1"
    )
    candidate_id: Identifier
    revision_round: int = Field(ge=0, le=3)
    context_configuration_ref: EvidenceRef
    memory: InactivePolicy
    model_allocation: AllocationToken
    parameters_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=10000)
    generation_seconds: int = Field(ge=1, le=600)
    interaction_seconds: int = Field(ge=1, le=180)
    cleanup_seconds: int = Field(ge=1, le=60)

    generation_budgets: ActorGenerationBudgets | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result = dict(handler(self))
        if self.generation_budgets is None:
            result.pop("generation_budgets", None)
        return result

    @model_validator(mode="after")
    def original(self) -> Self:
        if (
            self.generation_budgets is not None
            and self.generation_budgets.execution_seconds != self.generation_seconds
        ):
            raise ValueError(
                "Selected actual-call window differs from original generation duration"
            )
        private_state_ref(
            self.context_configuration_ref, "actor-context-configuration/1"
        )
        for ref in self.parameters_refs:
            private_state_ref(ref, "model-parameters/1")
        if any(
            ref.media_type != "application/json" or ref.size_bytes == 0
            for ref in (self.context_configuration_ref, *self.parameters_refs)
        ):
            raise ValueError(
                "Nonempty complete Actor configuration/parameters JSON required"
            )
        if self.context_configuration_ref.size_bytes > 16 * 1024**2:
            raise ValueError(
                "Actor context configuration exceeds its original complete bound"
            )
        token = self.model_allocation
        if (token.resource_kind, token.scope, token.attempt_id) != (
            "actor",
            "batch",
            None,
        ):
            raise ValueError(
                "Original registered batch Actor model allocation required"
            )
        return self


class TaskInitializationPlan(Contract):
    schema_version: Literal["task-initialization-plan/2"] = "task-initialization-plan/2"
    scope: StateScope
    prepared_result_ref: EvidenceRef
    source_context_receipt_ref: EvidenceRef
    browser_spec_ref: EvidenceRef
    browser_acquisition: OperationContext
    capture_operation: OperationContext
    initial_operation: OperationContext
    baseline_operation: OperationContext
    comparison_operation: OperationContext
    equivalence_operation: OperationContext
    actor: TaskActorInitialization

    @model_validator(mode="after")
    def original(self) -> Self:
        for ref, schema in (
            (self.prepared_result_ref, "site-task-prepared/2"),
            (self.source_context_receipt_ref, "public-context-receipt/1"),
            (self.browser_spec_ref, "browser-resource-spec/4"),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json" or ref.size_bytes == 0:
                raise ValueError(
                    "Original nonempty private initialization JSON required"
                )
        if self.scope.task.split != "train":
            raise ValueError("Current construction initialization is train-only")
        operations = (
            self.browser_acquisition,
            self.capture_operation,
            self.initial_operation,
            self.baseline_operation,
            self.comparison_operation,
            self.equivalence_operation,
        )
        if len({op.operation_id for op in operations}) != len(operations):
            raise ValueError(
                "Initial measurement stages require distinct original operations"
            )
        if any(
            (op.run_id, op.owner_id, op.attempt_id, op.mode)
            != (
                self.scope.owner.run_id,
                self.scope.owner.owner_id,
                self.scope.attempt_id,
                "execute",
            )
            for op in operations
        ):
            raise ValueError("Initialization changed original attempt execute scope")
        if (
            self.browser_acquisition.allocation_id is None
            or self.browser_acquisition.recovery_ref is None
            or (
                self.capture_operation.allocation_id,
                self.capture_operation.recovery_ref,
            )
            != (
                self.browser_acquisition.allocation_id,
                self.browser_acquisition.recovery_ref,
            )
        ):
            raise ValueError(
                "Initial capture requires original browser allocation/recovery"
            )
        if self.actor.model_allocation.owner != self.scope.owner:
            raise ValueError("Actor model changed original run/owner")
        if len(self.model_dump_json().encode()) > 2 * 1024**2:
            raise ValueError("Initialization declaration exceeds complete 2MiB bound")
        return self
