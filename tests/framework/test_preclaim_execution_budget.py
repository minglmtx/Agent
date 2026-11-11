"""No claim without preparation plus full execution; cleanup stays independent."""

from typing import Any

import pytest

from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.lifecycle import CancellationRef
from test_bounded_lifecycle import case


def test_boundary_repeat_and_partial_preparation_keep_cleanup() -> None:
    clock, _, controls, operation = case()
    original = controls.window
    assert (
        controls.require_execution_budget(
            operation, preparation_seconds=4, task_seconds=6
        )
        == 10
    )
    assert (
        controls.require_execution_budget(
            operation, preparation_seconds=4, task_seconds=6
        )
        == 10
    )
    clock.sleep(1)
    with pytest.raises(ValueError, match="Insufficient"):
        controls.require_execution_budget(
            operation, preparation_seconds=4, task_seconds=6
        )
    assert controls.window == original
    # Partial setup still uses the same bounded window and original close.
    clock.sleep(2)
    controls.narrow_execution(operation, seconds=6)
    clock.sleep(6)
    with pytest.raises(OperationStopped):
        controls.bind(operation).checkpoint()
    cleanup = operation.cleanup(
        "partial-prepare-close", now=clock.utcnow(), seconds=100
    )
    assert controls.bind(cleanup).checkpoint() == 9
    assert (
        controls.window.hard_end - controls.window.cleanup_deadline
    ).total_seconds() == 2


def test_cancel_refuses_claim_but_keeps_original_cleanup() -> None:
    clock, cancellation, controls, operation = case()
    cancellation.cancelled = True
    stopped = operation.model_copy(
        update={
            "cancellation_ref": CancellationRef(
                channel_id="stop", run_id=operation.run_id, owner_id=operation.owner_id
            )
        }
    )
    with pytest.raises(OperationStopped):
        controls.require_execution_budget(
            stopped, preparation_seconds=1, task_seconds=1
        )
    cleanup = stopped.cleanup("cancel-close", now=clock.utcnow(), seconds=100)
    assert controls.bind(cleanup).checkpoint() == 18


@pytest.mark.parametrize("value", [None, True, 0, -1, 86401, 1.5, "3"])
@pytest.mark.parametrize("field", ["preparation_seconds", "task_seconds"])
def test_invalid_budget_does_not_change_window(field: str, value: Any) -> None:
    _, _, controls, operation = case()
    before = controls.window
    args = dict(preparation_seconds=1, task_seconds=1)
    args[field] = value
    with pytest.raises(ValueError):
        controls.require_execution_budget(operation, **args)
    assert controls.window == before


def test_foreign_owner_and_cleanup_cannot_admit_work() -> None:
    clock, _, controls, operation = case()
    for other in (
        operation.model_copy(update={"owner_id": "foreign"}),
        operation.cleanup("close", now=clock.utcnow(), seconds=10),
    ):
        with pytest.raises(OwnershipConflict):
            controls.require_execution_budget(
                other, preparation_seconds=1, task_seconds=1
            )
