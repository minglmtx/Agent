"""Select and bind one Actor round without acquiring or replaying any producer."""

from dataclasses import dataclass
from datetime import timedelta
from lab_generate_skill.domain.actor_budget_stop import ActorRoundBudgetStopped
from lab_generate_skill.domain.actor_execution_window import ActorGenerationWindow
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControl,
    OperationControls,
)
from lab_generate_skill.policies.actor_preparation_budget import preparation_seconds
from .actor_generation_control import generation_preparation_control
from .actor_loop_inputs import actor_operation_id


@dataclass(frozen=True)
class RoundPreparation:
    operation: OperationContext
    window: ActorGenerationWindow | None
    control: OperationControl

    def bound(self, operation: OperationContext) -> OperationContext:
        if self.window is None:
            return operation
        return OperationContext.model_validate(
            operation.model_copy(
                update={
                    "deadline": min(
                        operation.deadline,
                        self.window.prepared_at
                        + timedelta(seconds=self.window.effective_preparation_seconds),
                    ),
                    "parent_operation_id": self.operation.operation_id,
                }
            )
        )


def select_round_preparation(
    request: ActorRunRequest,
    index: int,
    controls: OperationControls,
    clock: Clock,
) -> RoundPreparation:
    selected = request.generation_budgets
    parent = controls.bind(request.operation)
    remaining = parent.checkpoint()
    started = clock.utcnow()
    window = None
    if selected is not None:
        limit = preparation_seconds(
            selected, request.interaction_seconds, request.cleanup_seconds, remaining
        )
        if limit is None:
            raise ActorRoundBudgetStopped(
                request.operation.operation_id, index, "admission"
            )
        window = ActorGenerationWindow(
            schema_version="actor-generation-window/2",
            budgets=selected,
            prepared_at=started,
            preparation_limit_seconds=limit,
        )
    operation = OperationContext.model_validate(
        request.operation.model_copy(
            update={
                "operation_id": actor_operation_id(
                    request.operation.operation_id, f"turn-{index}-generate"
                ),
                "allocation_id": request.model_allocation.allocation_id,
                "recovery_ref": request.model_allocation.recovery_ref,
                "deadline": min(
                    request.operation.deadline,
                    started
                    + timedelta(
                        seconds=(
                            request.generation_seconds
                            if window is None
                            else window.transaction_seconds
                        )
                    ),
                ),
                **(
                    {"parent_operation_id": request.operation.operation_id}
                    if window is not None
                    else {}
                ),
            }
        )
    )
    return RoundPreparation(
        operation,
        window,
        generation_preparation_control(operation, window, controls.bind(operation)),
    )
