"""Common completed lifecycle facts; no candidate/Teacher/result mode policy.

A business adapter may publish its existing result envelope only after the full
lifecycle has sealed and the original Reset is confirmed. This fact does not
qualify a source, create a target or grant another execution.
"""

from typing import Literal, Self
from pydantic import Field, model_validator
from .task_intent import TaskAttemptIntent
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .initial_equivalence import private_equivalence_ref
from .validation import Contract


class TaskCompletionFacts(Contract):
    schema_version: Literal["task-completion-facts/1"] = "task-completion-facts/1"
    intent: TaskAttemptIntent
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
    def complete_original_facts(self) -> Self:
        for ref, schema in (
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
            self.plan_ref.visibility != "private"
            or self.actor_request_ref.visibility != "private"
        ):
            raise ValueError("Full original plan and Actor request remain private")
        if self.interactions > self.generations:
            raise ValueError("Completed task counters require original sealed trace")
        return self
