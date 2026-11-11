"""Existing owner controls see a finite later cap without rebinding inputs."""

from datetime import timedelta
from typing import Any
import pytest

from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.lifecycle import CancellationRef
from test_bounded_lifecycle import case


def test_prebound_owner_model_and_source_guards_all_observe_task_handoff() -> None:
    clock, _, controls, operation = case()
    original = operation.model_dump_json()
    root = controls.bind(operation)
    prior = operation.model_copy(update={"operation_id": "already-bound-source-read"})
    source = controls.bind(prior)
    clock.sleep(4)  # Preparation is inside the original job, before task start.
    window = controls.narrow_execution(operation, seconds=3)
    assert root.checkpoint() == source.checkpoint() == 3
    assert (
        controls.bind(
            operation.model_copy(update={"operation_id": "new-io"})
        ).checkpoint()
        == 3
    )
    assert window.cleanup_deadline == controls.window.cleanup_deadline
    assert operation.model_dump_json() == original
    clock.sleep(3)
    for guard in (root, source):
        with pytest.raises(OperationStopped):
            guard.checkpoint()
    cleanup = operation.cleanup("original-close", now=clock.utcnow(), seconds=100)
    assert controls.bind(cleanup).checkpoint() == 11
    assert (window.hard_end - clock.utcnow()).total_seconds() == 13


def test_insufficient_time_and_repeat_cannot_reset_window() -> None:
    clock, _, controls, operation = case()
    clock.sleep(4)
    before = controls.window
    with pytest.raises(ValueError, match="Insufficient"):
        controls.narrow_execution(operation, seconds=7)
    assert controls.window == before
    controls.narrow_execution(operation, seconds=5)
    clock.sleep(1)
    with pytest.raises(ValueError, match="Insufficient"):
        controls.narrow_execution(operation, seconds=5)
    assert controls.bind(operation).checkpoint() == 4
    controls.narrow_execution(operation, seconds=2)
    assert controls.bind(operation).checkpoint() == 2


def test_rollback_new_guards_and_cancel_still_use_original_stop_and_cleanup() -> None:
    clock, cancel, controls, operation = case()
    controls.narrow_execution(operation, seconds=6)
    clock.sleep(2)
    clock.wall -= timedelta(days=1)
    assert (
        controls.bind(
            operation.model_copy(update={"operation_id": "new-after-rollback"})
        ).checkpoint()
        == 4
    )
    cancel.cancelled = True
    cancelled = operation.model_copy(
        update={
            "operation_id": "cancelled",
            "cancellation_ref": CancellationRef(
                channel_id="stop", run_id=operation.run_id, owner_id=operation.owner_id
            ),
        }
    )
    with pytest.raises(OperationStopped):
        controls.narrow_execution(cancelled, seconds=1)
    cleanup = operation.cleanup("close-after-cancel", now=clock.utcnow(), seconds=100)
    assert controls.bind(cleanup).checkpoint() == 16


@pytest.mark.parametrize("seconds", [None, True, 0, -1, 86401, 1.5, "3"])
def test_bad_duration_has_no_effect(seconds: Any) -> None:
    _, _, controls, operation = case()
    before = controls.window
    with pytest.raises(ValueError):
        controls.narrow_execution(operation, seconds=seconds)
    assert controls.window == before


def test_cleanup_or_foreign_owner_cannot_change_execution_window() -> None:
    clock, _, controls, operation = case()
    before = controls.window
    for op in (
        operation.cleanup("close", now=clock.utcnow(), seconds=30),
        operation.model_copy(update={"owner_id": "foreign"}),
    ):
        with pytest.raises(OwnershipConflict):
            controls.narrow_execution(op, seconds=3)
    assert controls.window == before
