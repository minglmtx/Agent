"""Read-only original task-source view; never a reusable execution grant."""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract, Sha256
from .task import TaskBinding
from .task_intent import TaskAttemptIntent
from .evidence import EvidenceRef
from .state_scope import private_state_ref


class TaskPhaseSourceState(Contract):
    schema_version: Literal["task-phase-source-state/1"] = "task-phase-source-state/1"
    intent: TaskAttemptIntent
    task: TaskBinding
    public_context_ref: EvidenceRef
    context_receipt_ref: EvidenceRef
    source_sha256: Sha256

    @model_validator(mode="after")
    def original_source(self) -> Self:
        if (
            self.task.identity != self.intent.binding.task
            or self.public_context_ref != self.intent.public_context_ref
        ):
            raise ValueError("Task source view changed original task/public context")
        private_state_ref(self.context_receipt_ref, "public-context-receipt/1")
        return self
