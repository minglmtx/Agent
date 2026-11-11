"""Preparation is a bounded maximum; selected model and tail windows stay whole."""

from typing import Any
import pytest
from lab_generate_skill.domain.actor_execution_window import ActorGenerationBudgets
from lab_generate_skill.policies.actor_preparation_budget import preparation_seconds


def selected() -> ActorGenerationBudgets:
    return ActorGenerationBudgets(
        preparation_seconds=900, execution_seconds=600, retention_seconds=300
    )


@pytest.mark.parametrize(
    "remaining,expected",
    [
        (2220, 900),
        (2219, 899),
        (1500, 180),
        (1321, 1),
        (1320, None),
        (1319, None),
        (1320.9, None),
        (1321.9, 1),
        (2220.9, 900),
        (0, None),
        (-1, None),
        (10**15, 900),
    ],
)
def test_complete_model_and_tail_reserved_before_bounded_preparation(
    remaining: float, expected: int | None
) -> None:
    budgets = selected()
    before = budgets.model_dump_json()
    for _ in range(2):
        actual = preparation_seconds(budgets, 180, 60, remaining)
        assert actual == expected
        if actual is not None:
            assert 1 <= actual <= 900 and actual + 600 + 300 + 180 + 4 * 60 <= remaining
    assert budgets.model_dump_json() == before


@pytest.mark.parametrize("value", [None, True, "1500", [], {}])
def test_wrong_remaining_type_is_rejected(value: Any) -> None:
    with pytest.raises(TypeError):
        preparation_seconds(selected(), 180, 60, value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_remaining_cannot_grant_a_preparation(value: float) -> None:
    with pytest.raises(ValueError):
        preparation_seconds(selected(), 180, 60, value)


@pytest.mark.parametrize(
    "interaction,cleanup,error",
    [
        (0, 60, ValueError),
        (180, -1, ValueError),
        (True, 60, TypeError),
        (180, 1.5, TypeError),
    ],
)
def test_invalid_tail_is_not_silently_shortened(
    interaction: Any, cleanup: Any, error: type[Exception]
) -> None:
    with pytest.raises(error):
        preparation_seconds(selected(), interaction, cleanup, 1500)


@pytest.mark.parametrize("retention,expected", [(20, 27), (None, 45)])
def test_exact_selected_and_legacy_return_profiles_are_used(
    retention: int | None, expected: int
) -> None:
    budgets = ActorGenerationBudgets(
        preparation_seconds=45, execution_seconds=120, retention_seconds=retention
    )
    assert preparation_seconds(budgets, 5, 2, 180) == expected
