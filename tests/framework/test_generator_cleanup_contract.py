"""Owned cleanup handoff rejects ambiguous or coercible identities."""

import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.generator_step import GeneratorStepCleanup


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"start_attempted": None},
        {"start_attempted": 0},
        {"start_attempted": "false"},
        {"start_attempted": False, "target": {}},
        {"start_attempted": False, "launcher": {}},
        {"start_attempted": False, "started": {}},
        {"start_attempted": False, "unknown": 1},
    ],
)
def test_invalid_cleanup(value: object) -> None:
    with pytest.raises(ValidationError):
        GeneratorStepCleanup.model_validate(value)


@pytest.mark.parametrize("attempted", [False, True])
def test_cleanup_unknown_is_not_closure(attempted: bool) -> None:
    value = GeneratorStepCleanup(start_attempted=attempted)
    assert value.target is None
    assert GeneratorStepCleanup.model_validate_json(value.model_dump_json()) == value
