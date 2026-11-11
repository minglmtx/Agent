"""Frozen cleanup stage and input boundaries; no resource/model effects."""

from typing import Any
import pytest
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from state_contract_fixtures import scope


def declaration() -> TaskFinalizationPlan:
    return TaskFinalizationPlan(
        scope=scope(),
        browser_close_operation_id="task-browser-close",
        restore_operation_id="task-restore",
        resume_operation_id="task-resume",
        qualification_operation_id="task-reset-facts",
        reset_operation_id="task-reset",
    )


def test_finalization_plan_roundtrip_and_identifier_room() -> None:
    plan = declaration()
    assert TaskFinalizationPlan.model_validate_json(plan.model_dump_json()) == plan
    data = plan.model_dump()
    data["restore_operation_id"] = "r" * 180
    assert TaskFinalizationPlan.model_validate(data).restore_operation_id == "r" * 180


@pytest.mark.parametrize("value", [None, "", [], {}, True, 1])
def test_empty_and_wrong_finalization_plan_rejected(value: Any) -> None:
    with pytest.raises(ValueError):
        TaskFinalizationPlan.model_validate(value)


@pytest.mark.parametrize(
    "change",
    [
        {"restore_operation_id": "task-resume"},
        {"resume_operation_id": ""},
        {"reset_operation_id": "r" * 181},
        {"browser_close_operation_id": None},
        {"extra": True},
    ],
)
def test_duplicate_or_illegal_cleanup_plan_fields_fail(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TaskFinalizationPlan.model_validate({**declaration().model_dump(), **change})


@pytest.mark.parametrize("split", ["dev", "test"])
def test_finalization_does_not_promote_non_train(split: str) -> None:
    plan = declaration()
    with pytest.raises(ValueError):
        TaskFinalizationPlan.model_validate(
            {
                **plan.model_dump(),
                "scope": plan.scope.model_copy(
                    update={"task": plan.scope.task.model_copy(update={"split": split})}
                ),
            }
        )
