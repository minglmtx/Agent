"""Original candidate task lifecycle data; references never confer execution rights."""

from typing import Literal, Self, Any
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .actor_run import ActorRunRequest
from .task_intent import TaskAttemptIntent as AttemptIntent
from .evidence import EvidenceRef
from .evaluation import EvaluationContract
from .lifecycle import OperationContext, ClosureReceipt
from .reset import ResetPlan
from .state_scope import private_state_ref
from .initial_equivalence import private_equivalence_ref
from .validation import Contract


class TaskExecutionPlan(Contract):
    schema_version: Literal["task-execution-plan/1", "task-execution-plan/2"] = (
        "task-execution-plan/1"
    )
    intent: AttemptIntent
    reset_plan_ref: EvidenceRef
    declaration_ref: EvidenceRef
    skill_ref: EvidenceRef
    evaluation: EvaluationContract
    operation: OperationContext
    read_operation: OperationContext
    cleanup_seconds: int = Field(ge=1, le=3600)
    source_ref: EvidenceRef | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.schema_version == "task-execution-plan/1":
            data.pop("source_ref", None)
        return data

    @model_validator(mode="after")
    def original_scope(self) -> Self:
        execution = self.intent.source_kind == "execution"
        if execution != (self.schema_version == "task-execution-plan/2"):
            raise ValueError("Task plan version must bind its actual source mode")
        if execution:
            if self.source_ref is None:
                raise ValueError("Single task requires its original execution source")
            if self.source_ref.content_schema not in (
                "execution-task-source/1",
                "execution-task-source/2",
            ):
                raise ValueError("Unsupported explicit execution source version")
            private_state_ref(self.source_ref, self.source_ref.content_schema)
        elif "source_ref" in self.model_fields_set:
            raise ValueError("Original construction plan forbids execution-only fields")
        binding, op, read = self.intent.binding, self.operation, self.read_operation
        owner = binding.run.owner
        private_state_ref(self.reset_plan_ref, "reset-plan/1")
        if self.declaration_ref.visibility != "private":
            raise ValueError("Original task initialization declaration stays private")
        if (self.skill_ref.visibility, self.skill_ref.content_schema) != (
            "public",
            "compact-skill/1",
        ):
            raise ValueError("Task execution needs the original public candidate skill")
        if (self.evaluation.identity, self.evaluation.attempt_id) != (
            binding.task,
            binding.attempt_id,
        ):
            raise ValueError("Task judgment must bind the exact original attempt")
        if (
            op.run_id,
            op.owner_id,
            op.attempt_id,
            op.mode,
            op.allocation_id,
            op.recovery_ref,
        ) != (owner.run_id, owner.owner_id, binding.attempt_id, "execute", None, None):
            raise ValueError("Task lifecycle needs its original attempt execute scope")
        if (
            read.run_id,
            read.owner_id,
            read.attempt_id,
            read.allocation_id,
            read.recovery_ref,
        ) != (
            owner.run_id,
            owner.owner_id,
            None,
            None,
            None,
        ) or read.operation_id == op.operation_id:
            raise ValueError(
                "Task journal reads need an independent original run scope"
            )
        if len(op.operation_id) > 200:
            raise ValueError(
                "Task operation must leave room for fixed phase identities"
            )
        return self


class InitializedTask(Contract):
    schema_version: Literal["initialized-task/1"] = "initialized-task/1"
    baseline_ref: EvidenceRef
    equivalence_ref: EvidenceRef
    actor: ActorRunRequest

    @model_validator(mode="after")
    def original_baseline(self) -> Self:
        private_state_ref(self.baseline_ref, "baseline-receipt/1")
        private_equivalence_ref(self.equivalence_ref)
        return self


class TaskCaptureResult(Contract):
    schema_version: Literal["task-capture-result/1"] = "task-capture-result/1"
    contract: EvaluationContract
    references: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=10000)


class ClosedTaskResources(Contract):
    schema_version: Literal["closed-task-resources/1"] = "closed-task-resources/1"
    reset_plan: ResetPlan
    reset_plan_ref: EvidenceRef
    closures: tuple[ClosureReceipt, ...] = Field(min_length=1)
    closure_refs: tuple[EvidenceRef, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def all_original_allocations(self) -> Self:
        private_state_ref(self.reset_plan_ref, "reset-plan/1")
        if tuple(
            c.token for c in self.closures
        ) != self.reset_plan.attempt_allocations or len(self.closure_refs) != len(
            self.closures
        ):
            raise ValueError(
                "Task closure requires every original attempt allocation in order"
            )
        if len(set(self.closure_refs)) != len(self.closure_refs) or any(
            c.status != "closed" for c in self.closures
        ):
            raise ValueError(
                "Unknown or duplicate closure cannot authorize restoration"
            )
        for ref in self.closure_refs:
            private_state_ref(ref, "closure-receipt/1")
        return self
