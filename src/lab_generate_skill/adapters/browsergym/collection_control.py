"""One declared collection lifetime, independent of its shorter acquisition.

The lifetime is frozen before acquisition, never renewed by an action. Each
existing caller retains its own stricter deadline and cancellation checks.
"""

from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl, Clock
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.combined_control import CombinedControl


class OriginalMapCollectionControl:
    def __init__(self, operation: OperationContext, clock: Clock) -> None:
        self.operation = OperationContext.model_validate(operation)
        self.bound = DeadlineControl(
            (self.operation.deadline - clock.utcnow()).total_seconds(),
            self.operation.operation_id,
        )

    def checkpoint(self) -> float:
        return self.bound.checkpoint()

    def wait(self, seconds: float) -> None:
        self.bound.wait(seconds)

    def intersect(self, caller: OperationControl) -> OperationControl:
        return CombinedControl(caller, self.bound)
