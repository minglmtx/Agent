"""Bound preparation after reserving the complete selected call and result tail."""

import math
from lab_generate_skill.domain.actor_execution_window import ActorGenerationBudgets


def preparation_seconds(
    budgets: ActorGenerationBudgets,
    interaction_seconds: int,
    cleanup_seconds: int,
    remaining_seconds: float,
) -> int | None:
    """Return this preparation's upper bound, or no new-round admission.

    This pure choice grants no send. The actual dispatcher must check the
    original parent again and preserve the complete selected execution window.
    """
    budgets = ActorGenerationBudgets.model_validate(budgets)
    for value in (interaction_seconds, cleanup_seconds):
        if type(value) is not int:
            raise TypeError("Actor tail budgets must be integer seconds")
        if value <= 0:
            raise ValueError("Actor tail budgets must be positive")
    if type(remaining_seconds) not in (int, float):
        raise TypeError("Original remaining time must be a number")
    if not math.isfinite(remaining_seconds):
        raise ValueError("Original remaining time must be finite")
    reserved = (
        budgets.execution_seconds
        + budgets.return_seconds(cleanup_seconds)
        + interaction_seconds
        + 4 * cleanup_seconds
    )
    available = remaining_seconds - reserved
    if available < 1:
        return None
    return min(budgets.preparation_seconds, math.floor(available))
