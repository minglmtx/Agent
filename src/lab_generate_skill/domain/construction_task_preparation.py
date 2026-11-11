"""Original already-frozen Task plan -> saved construction command, no new grant."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .construction import AttemptPlanned
from .construction_control import ConstructionStepPlan, ExecuteConstructionWork
from .execution import RunBinding
from .lifecycle import OperationContext
from .task_execution import TaskExecutionPlan
from .validation import Contract


class ActorPreparation(Contract):
    schema_version: Literal["construction-task-preparation/1"] = (
        "construction-task-preparation/1"
    )
    run: RunBinding
    expected_revision: int = Field(ge=-1, le=255)
    task: TaskExecutionPlan
    operation: OperationContext
    completion_operation: OperationContext

    @model_validator(mode="after")
    def original_operations(self) -> Self:
        # Reuse the original command's scope/parent/distinct-ID rules. Validation
        # constructs data only; registration remains with construct_targets.
        self.step()
        if len(self.model_dump_json().encode()) > 4 * 1024**2:
            raise ValueError("Complete task preparation exceeds metadata bound")
        return self

    def step(self) -> ConstructionStepPlan:
        return ConstructionStepPlan(
            run=self.run,
            expected_revision=self.expected_revision,
            operation=self.operation,
            work=ExecuteConstructionWork(
                planned=AttemptPlanned(
                    operation=self.operation, intent=self.task.intent
                ),
                invoke_operation=self.task.operation,
                completion_operation=self.completion_operation,
            ),
        )
