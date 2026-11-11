"""Consume the existing initialized body within its original owned task scope."""

from collections.abc import Callable
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.initial_observation import (
    InitialObservationInputs,
    InitialObservationSelection,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from .task_initialization import RecordedTaskInitialization
from .task_initialization_inputs import TaskInitializationInputs


class TaskCaptureInitialReads:
    """No source/claim verdict, new observation, fallback or retained permission."""

    def __init__(
        self,
        plan: TaskExecutionPlan,
        inputs: TaskInitializationInputs,
        initialization: Callable[[], RecordedTaskInitialization],
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        if inputs.plan != self.plan or not callable(initialization):
            raise OwnershipConflict("Capture initial body changed original task scope")
        self.inputs, self.initialization = inputs, initialization

    def load(
        self,
        selection: InitialObservationSelection,
        operation: OperationContext,
        control: OperationControl,
    ) -> InitialObservationInputs:
        selection = InitialObservationSelection.model_validate(selection)
        operation = OperationContext.model_validate(operation)
        self.inputs.check(operation, control)
        original = self.initialization()
        if (
            original.plan != self.plan
            or original.inputs is not self.inputs
            or original.state.phase != "initialized"
            or original.state.result is None
            or original.state.selection != selection
        ):
            raise OwnershipConflict("Original completed initial producer required")
        current = original.current_initial_observation(operation, control)
        if current is None:
            raise OwnershipConflict("Selected capture initial body is unavailable")
        current = InitialObservationInputs.model_validate(current)
        if (
            current.selection != selection
            or current.prepared.scope != original.state.result.actor.scope
            or current.prepared.public_task != original.state.result.actor.task
        ):
            raise OwnershipConflict("Capture initial body changed original content")
        self.inputs.check(operation, control)
        return current
