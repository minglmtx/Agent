"""Explicit serial execution budgets; permissions and cleanup remain separate."""

from typing import Literal
from pydantic import Field
from .validation import Contract

ExecutionStage = Literal[
    "assets",
    "source",
    "model",
    "preparation",
    "initialization",
    "actor",
    "capture",
    "judgment",
]
STAGES: tuple[ExecutionStage, ...] = (
    "assets",
    "source",
    "model",
    "preparation",
    "initialization",
    "actor",
    "capture",
    "judgment",
)


class ExecutionStageBudgets(Contract):
    schema_version: Literal["execution-stage-budgets/1"] = "execution-stage-budgets/1"
    assets_seconds: int = Field(gt=0, le=86400)
    source_seconds: int = Field(gt=0, le=86400)
    model_seconds: int = Field(gt=0, le=86400)
    preparation_seconds: int = Field(gt=0, le=86400)
    initialization_seconds: int = Field(gt=0, le=86400)
    actor_seconds: int = Field(gt=0, le=86400)
    capture_seconds: int = Field(gt=0, le=86400)
    judgment_seconds: int = Field(gt=0, le=86400)
    task_orchestration_seconds: int = Field(gt=0, le=3600)

    def seconds(self, stage: ExecutionStage) -> int:
        if stage not in STAGES:
            raise ValueError("Unknown execution stage")
        values = (
            self.assets_seconds,
            self.source_seconds,
            self.model_seconds,
            self.preparation_seconds,
            self.initialization_seconds,
            self.actor_seconds,
            self.capture_seconds,
            self.judgment_seconds,
        )
        return values[STAGES.index(stage)]

    @property
    def task_seconds(self) -> int:
        return self.task_orchestration_seconds + sum(
            self.seconds(s) for s in STAGES[3:]
        )

    @property
    def execution_seconds(self) -> int:
        return (
            self.assets_seconds
            + self.source_seconds
            + self.model_seconds
            + self.task_seconds
        )

    def reserve_after(self, stage: ExecutionStage) -> int:
        if stage not in STAGES:
            raise ValueError("Unknown execution stage")
        return sum(self.seconds(s) for s in STAGES[STAGES.index(stage) + 1 :]) + (
            self.task_orchestration_seconds if stage in STAGES[:3] else 0
        )
