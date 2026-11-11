"""Single execution outcome; never a construction/Teacher training target."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .task_intent import TaskAttemptIntent
from .evidence import EvidenceRef
from .evaluation import Evaluation
from .state_scope import private_state_ref


class ExecutionTaskResult(Contract):
    schema_version: Literal["execution-task-result/1"] = "execution-task-result/1"
    intent: TaskAttemptIntent
    attempt_ref: EvidenceRef
    evaluation: Evaluation
    evaluation_ref: EvidenceRef
    interactions: int = Field(ge=0)
    generations: int = Field(ge=0)

    @model_validator(mode="after")
    def original_execution(self) -> Self:
        if self.intent.source_kind != "execution":
            raise ValueError("Execution result requires its actual execution intent")
        private_state_ref(self.attempt_ref, "execution-attempt-result/1")
        private_state_ref(self.evaluation_ref, "evaluation/1")
        if (
            self.evaluation.identity != self.intent.binding.task
            or self.evaluation.attempt_id != self.intent.binding.attempt_id
            or self.interactions > self.generations
        ):
            raise ValueError("Execution judgment/counters changed original task")
        return self
