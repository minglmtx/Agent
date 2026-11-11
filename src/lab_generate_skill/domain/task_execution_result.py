"""Concrete original task result; historical unit attempt JSON is not upgraded."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .task_intent import TaskAttemptIntent as AttemptIntent
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .initial_equivalence import private_equivalence_ref
from .validation import Contract
from .validation import NonEmptyText


class TaskFailureContext(Contract):
    """Full attributable graph outside the bounded run-journal event.

    No raw backend exception text/credentials. The original exception and cause
    chain remain on TaskExecutionUnconfirmed; native diagnostic references and
    every known immutable fact remain in this complete private CAS document.
    """

    schema_version: Literal["task-failure-context/1", "task-failure-context/2"] = (
        "task-failure-context/1"
    )
    intent: AttemptIntent
    failure_type: NonEmptyText
    references: tuple[EvidenceRef, ...] = Field(max_length=10000)

    @model_validator(mode="after")
    def source_variant(self) -> Self:
        if (self.schema_version == "task-failure-context/2") != (
            self.intent.source_kind == "execution"
        ):
            raise ValueError("Task failure must retain its actual source mode")
        return self


class ExecutedTaskReceipt(Contract):
    schema_version: Literal["executed-task-receipt/1", "executed-task-receipt/2"] = (
        "executed-task-receipt/1"
    )
    intent: AttemptIntent
    plan_ref: EvidenceRef
    actor_request_ref: EvidenceRef
    baseline_ref: EvidenceRef
    equivalence_ref: EvidenceRef
    trace_ref: EvidenceRef
    capture_ref: EvidenceRef
    evaluation_ref: EvidenceRef
    closed_ref: EvidenceRef
    reset_ref: EvidenceRef
    generations: int = Field(ge=0)
    interactions: int = Field(ge=0)

    @model_validator(mode="after")
    def explicit_original_facts(self) -> Self:
        execution = self.intent.source_kind == "execution"
        if execution != (self.schema_version == "executed-task-receipt/2"):
            raise ValueError("Task receipt version changed its actual source")
        for ref, schema in (
            (
                self.plan_ref,
                "task-execution-plan/2" if execution else "task-execution-plan/1",
            ),
            (self.baseline_ref, "baseline-receipt/1"),
            (self.trace_ref, "interaction-trace/1"),
            (self.capture_ref, "task-capture-result/1"),
            (self.evaluation_ref, "evaluation/1"),
            (self.closed_ref, "closed-task-resources/1"),
            (self.reset_ref, "reset-receipt/1"),
        ):
            private_state_ref(ref, schema)
        if self.intent.source_kind == "execution":
            private_equivalence_ref(self.equivalence_ref)
        else:
            private_state_ref(self.equivalence_ref, "equivalence-receipt/1")
        if (
            self.actor_request_ref.visibility != "private"
            or self.actor_request_ref.content_schema
            not in ("actor-run-request/1", "actor-run-request/2")
        ):
            raise ValueError("Task result requires the exact original Actor request")
        if self.interactions > self.generations:
            raise ValueError("Task result counters must derive from the original trace")
        return self


class TaskAttemptResult(Contract):
    """Original attempt-result envelope points to an explicitly versioned native record.

    Old synthetic unit_closed envelopes remain old evidence, never inferred here.
    """

    schema_version: Literal["attempt-result/1", "execution-attempt-result/1"] = (
        "attempt-result/1"
    )
    intent: AttemptIntent
    execution_ref: EvidenceRef
    interactions: int = Field(ge=0)
    generations: int = Field(ge=0)

    @model_validator(mode="after")
    def full_execution_reference(self) -> Self:
        execution = self.intent.source_kind == "execution"
        if execution != (self.schema_version == "execution-attempt-result/1"):
            raise ValueError("Attempt envelope must retain its source mode")
        private_state_ref(
            self.execution_ref,
            "executed-task-receipt/2" if execution else "executed-task-receipt/1",
        )
        if self.interactions > self.generations:
            raise ValueError("Task counters cannot exceed original generations")
        return self
