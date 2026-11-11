"""Frozen capture schema boundaries; no resource/source/model effects."""

from typing import Any
import pytest
from lab_generate_skill.domain.task_capture import TaskCapturePlan
from lab_generate_skill.evaluators.map.navigation import REQUIREMENTS
from state_contract_fixtures import scope


def declaration() -> TaskCapturePlan:
    return TaskCapturePlan(
        scope=scope(),
        requirements=REQUIREMENTS,
        page_operation_id="terminal-page",
        close_operation_id="terminal-close",
        guard_operation_id="terminal-guard",
        page_collector_id="map-navigation-page-health",
        page_collector_version="1",
        guard_collector_id="map-navigation-state",
        guard_collector_version="1",
        close_seconds=30,
    )


def test_complete_capture_plan_roundtrip_and_fixed_bounds() -> None:
    value = declaration()
    assert TaskCapturePlan.model_validate_json(value.model_dump_json()) == value
    extreme = value.model_copy(
        update={
            "page_operation_id": "p" * 200,
            "close_operation_id": "c" * 200,
            "guard_operation_id": "g" * 200,
            "close_seconds": 60,
        }
    )
    assert TaskCapturePlan.model_validate(extreme) == extreme


@pytest.mark.parametrize("value", [None, "", [], {}, True, 1])
def test_empty_wrong_capture_plan_fails_without_effect(value: Any) -> None:
    with pytest.raises(ValueError):
        TaskCapturePlan.model_validate(value)


@pytest.mark.parametrize(
    "change",
    [
        {"close_seconds": 0},
        {"close_seconds": 61},
        {"close_seconds": True},
        {"close_seconds": "30"},
        {"page_collector_id": ""},
        {"page_collector_version": ""},
        {"guard_collector_version": None},
        {"page_operation_id": "terminal-close"},
        {"guard_operation_id": "p" * 201},
        {"requirements": None},
        {"requirements": []},
    ],
)
def test_illegal_capture_fields_or_duplicate_operations_rejected(
    change: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        TaskCapturePlan.model_validate({**declaration().model_dump(), **change})


def test_dev_test_capture_not_promoted_to_train() -> None:
    value = declaration()
    for split in ("dev", "test"):
        with pytest.raises(ValueError):
            TaskCapturePlan.model_validate(
                {
                    **value.model_dump(),
                    "scope": value.scope.model_copy(
                        update={
                            "task": value.scope.task.model_copy(update={"split": split})
                        }
                    ),
                }
            )
