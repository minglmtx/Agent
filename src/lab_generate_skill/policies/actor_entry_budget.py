"""Pure admission of one complete selected Actor round before entry effects."""

from lab_generate_skill.domain.actor_execution_window import ActorGenerationBudgets


def checked_actor_round_budgets(
    selected: ActorGenerationBudgets | None,
    generation_seconds: int,
    interaction_seconds: int,
    cleanup_seconds: int,
    available_seconds: int,
) -> ActorGenerationBudgets | None:
    if selected is None:
        return None
    budgets = ActorGenerationBudgets.model_validate(selected)
    for value, maximum in (
        (generation_seconds, 600),
        (interaction_seconds, 180),
        (cleanup_seconds, 60),
        (available_seconds, 86400),
    ):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError("Explicit bounded Actor round budgets required")
    if budgets.execution_seconds != generation_seconds:
        raise ValueError("Actor execution window differs from generation budget")
    if budgets.round_seconds(interaction_seconds, cleanup_seconds) > available_seconds:
        raise ValueError("Actor stage cannot fit a complete round and result closure")
    return budgets
