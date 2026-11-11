"""Reserve the fixed call window while preparing its original transaction."""

import math
from lab_generate_skill.domain.actor_execution_window import ActorGenerationWindow
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl


class GenerationPreparationControl:
    def __init__(
        self,
        original: OperationContext,
        selected: ActorGenerationWindow,
        parent: OperationControl,
    ) -> None:
        selected.require_original(original)
        self.original, self.selected, self.parent = original, selected, parent

    def checkpoint(self) -> float:
        remaining = self.parent.checkpoint() - self.selected.budgets.execution_seconds
        if remaining <= 0:
            raise OperationStopped("DEADLINE_EXCEEDED", self.original.operation_id)
        return min(remaining, float(self.selected.effective_preparation_seconds))

    def wait(self, seconds: float) -> None:
        if not isinstance(seconds, (int, float)):
            raise TypeError("Wait duration must be an int or float")
        try:
            if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds < 0:
                raise ValueError("Wait duration must be nonnegative and finite")
        except OverflowError as error:
            raise ValueError("Wait duration is outside the supported range") from error
        self.parent.wait(min(seconds, self.checkpoint()))
        self.checkpoint()


def generation_preparation_control(
    original: OperationContext,
    selected: ActorGenerationWindow | None,
    parent: OperationControl,
) -> OperationControl:
    if selected is None:
        return parent
    if isinstance(parent, GenerationPreparationControl):
        if parent.original != original or parent.selected != selected:
            raise OwnershipConflict("Preparation control changed its original window")
        return parent
    return GenerationPreparationControl(original, selected, parent)
