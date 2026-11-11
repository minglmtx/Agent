"""Fixed job end, original identities, live stop and finite cleanup reserve."""

from datetime import datetime, timedelta, timezone
import os
import signal
from typing import cast

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceOwner
from lab_generate_skill.domain.operation_window import (
    OperationTimeWindow,
    OperationWindowBudgets,
)
from lab_generate_skill.runtime.bounded_lifecycle import BoundedOperationControls
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_lifecycle import ManualClock, CancelSwitch


def owner() -> ResourceOwner:
    return ResourceOwner(
        run_id="bounded-run",
        owner_id="original-owner",
        job_id="123",
        worker_id="worker",
    )


def budgets() -> OperationWindowBudgets:
    # Unit-only 10s execution + 8s composed cleanup + 2s final reserve.
    return OperationWindowBudgets(
        execution_seconds=10,
        cleanup_seconds=8,
        final_margin_seconds=2,
        stop_signal_lead_seconds=10,
    )


def case() -> (
    tuple[ManualClock, CancelSwitch, BoundedOperationControls, OperationContext]
):
    clock, cancellation = ManualClock(), CancelSwitch()
    window = budgets().window(
        owner(), now=clock.utcnow(), hard_end=clock.utcnow() + timedelta(seconds=20)
    )
    controls = BoundedOperationControls(
        OperationGuards(clock, cancellation), clock, window
    )
    operation = OperationContext(
        operation_id="execute",
        run_id=owner().run_id,
        owner_id=owner().owner_id,
        deadline=clock.utcnow() + timedelta(seconds=100),
    )
    return clock, cancellation, controls, operation


def test_exact_budget_and_repeated_binding_keep_original_context() -> None:
    clock, _, controls, operation = case()
    original = operation.model_dump_json()
    first = controls.bind(operation)
    assert controls.bind(operation) is first
    assert first.checkpoint() == 10
    clock.sleep(3)
    assert first.checkpoint() == 7
    assert operation.model_dump_json() == original
    earlier = operation.model_copy(
        update={
            "operation_id": "earlier",
            "deadline": clock.utcnow() + timedelta(seconds=2),
        }
    )
    assert controls.bind(earlier).checkpoint() == 2
    with pytest.raises(OwnershipConflict):
        controls.bind(
            operation.model_copy(
                update={"deadline": operation.deadline + timedelta(seconds=1)}
            )
        )


def test_expiry_leaves_original_cleanup_and_margin_then_stops_cleanup() -> None:
    clock, _, controls, operation = case()
    clock.sleep(10)
    with pytest.raises(OperationStopped):
        controls.bind(operation).checkpoint()
    cleanup = operation.cleanup("original.restore", now=clock.utcnow(), seconds=100)
    assert cleanup.parent_operation_id == operation.operation_id
    guard = controls.bind(cleanup)
    assert guard.checkpoint() == 8
    with pytest.raises(OperationStopped):
        guard.wait(100)
    assert clock.elapsed == 18
    # Fresh cleanup identity cannot reset the shared cutoff or use the margin.
    with pytest.raises(OperationStopped):
        controls.bind(
            cleanup.cleanup("original.final-record", now=clock.utcnow(), seconds=100)
        ).checkpoint()
    assert (controls.window.hard_end - clock.utcnow()).total_seconds() == 2


def test_new_child_after_wall_clock_rollback_does_not_gain_time() -> None:
    clock, _, controls, operation = case()
    clock.sleep(9)
    clock.wall -= timedelta(days=1)
    late = operation.model_copy(update={"operation_id": "late-child"})
    assert controls.bind(late).checkpoint() == 1
    clock.sleep(1)
    with pytest.raises(OperationStopped):
        controls.bind(operation).checkpoint()
    cleanup = operation.cleanup(
        "restore-after-rollback", now=clock.utcnow(), seconds=100
    )
    assert controls.bind(cleanup).checkpoint() == 8


def test_actual_outer_stop_signal_does_not_cancel_cleanup() -> None:
    from production_runtime import OriginalSignalCancellation

    clock = ManualClock()
    window = budgets().window(
        owner(), now=clock.utcnow(), hard_end=clock.utcnow() + timedelta(seconds=20)
    )
    previous = signal.getsignal(signal.SIGUSR1)
    with OriginalSignalCancellation(owner()) as cancellation:
        controls = BoundedOperationControls(
            OperationGuards(clock, cancellation), clock, window
        )
        operation = OperationContext(
            operation_id="signal-body",
            run_id=owner().run_id,
            owner_id=owner().owner_id,
            cancellation_ref=cancellation.reference,
            deadline=window.execution_deadline,
        )
        os.kill(os.getpid(), signal.SIGUSR1)
        with pytest.raises(OperationStopped) as stopped:
            controls.bind(operation).checkpoint()
        assert stopped.value.reason_code == "CANCELLED"
        assert len(cancellation.signals) == 1
        cleanup = operation.cleanup("signal-close", now=clock.utcnow(), seconds=100)
        assert controls.bind(cleanup).checkpoint() == 18
    assert signal.getsignal(signal.SIGUSR1) == previous


def test_partial_commit_and_serial_cleanup_keep_primary_and_original_once() -> None:
    clock, _, controls, operation = case()
    committed: list[str] = []
    receipts: list[str] = []
    primary = RuntimeError("restore committed but original return lost")
    cleanup = operation.cleanup("restore", now=clock.utcnow(), seconds=100)
    clock.sleep(10)
    try:
        controls.bind(cleanup).checkpoint()
        committed.append("original-instance")
        clock.sleep(4)
        raise primary
    except RuntimeError as error:
        assert error is primary
        # Unknown restore is not replayed or resumed. Original resource closing
        # may still run; a later phase gets only the remaining shared reserve.
        closing = operation.cleanup("site-close", now=clock.utcnow(), seconds=100)
        assert controls.bind(closing).checkpoint() == 4
        receipts.append("original-site-closed")
        clock.sleep(4)
        with pytest.raises(OperationStopped):
            controls.bind(
                operation.cleanup("late-review", now=clock.utcnow(), seconds=100)
            ).checkpoint()
    assert committed == ["original-instance"] and receipts == ["original-site-closed"]


@pytest.mark.parametrize(
    "field", ["execution_deadline", "cleanup_deadline", "hard_end"]
)
@pytest.mark.parametrize("bad", [None, "", 0, True, datetime(2026, 1, 1)])
def test_window_missing_or_wrong_timestamp(field: str, bad: object) -> None:
    _, _, controls, _ = case()
    values = controls.window.model_dump()
    values[field] = bad
    with pytest.raises(ValidationError):
        OperationTimeWindow.model_validate(values)


@pytest.mark.parametrize(
    "field",
    [
        "execution_seconds",
        "cleanup_seconds",
        "final_margin_seconds",
        "stop_signal_lead_seconds",
    ],
)
@pytest.mark.parametrize("bad", [None, "1", True, 0, -1, 86401, float("nan")])
def test_budget_strict_missing_and_invalid(field: str, bad: object) -> None:
    values = budgets().model_dump()
    values[field] = bad
    with pytest.raises(ValidationError):
        OperationWindowBudgets.model_validate(values)
    del values[field]
    with pytest.raises(ValidationError):
        OperationWindowBudgets.model_validate(values)


def test_signal_and_remaining_budget_inconsistency_rejected_before_consumers() -> None:
    values = budgets().model_dump()
    values["stop_signal_lead_seconds"] = 9
    with pytest.raises(ValidationError):
        OperationWindowBudgets.model_validate(values)
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="Insufficient"):
        budgets().window(owner(), now=now, hard_end=now + timedelta(seconds=19.999))
    assert budgets().minimum_remaining_seconds == 20
    copied = budgets().model_copy(update={"execution_seconds": True})
    with pytest.raises(ValidationError):
        copied.window(owner(), now=now, hard_end=now + timedelta(seconds=20))
    with pytest.raises(ValueError):
        BoundedOperationControls(
            OperationGuards(ManualClock(), CancelSwitch()),
            ManualClock(),
            budgets()
            .window(owner(), now=now, hard_end=now + timedelta(seconds=20))
            .model_copy(
                update={"execution_deadline": datetime(2020, 1, 1, tzinfo=timezone.utc)}
            ),
        )


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), 10**400])
def test_nonfinite_monotonic_clock_rejected_at_creation_and_use(bad: object) -> None:
    clock, _, controls, operation = case()
    clock.elapsed = cast(float, bad)
    with pytest.raises(ValueError):
        controls.bind(operation).checkpoint()
    with pytest.raises(ValueError):
        BoundedOperationControls(
            OperationGuards(clock, CancelSwitch()), clock, controls.window
        )


@pytest.mark.parametrize(
    "bad", [True, None, "", -1, float("nan"), float("inf"), 10**400]
)
def test_invalid_wait_has_no_clock_or_effect(bad: object) -> None:
    clock, _, controls, operation = case()
    with pytest.raises(ValueError):
        controls.bind(operation).wait(cast(float, bad))
    assert clock.elapsed == 0


def test_foreign_owner_and_unordered_window_rejected() -> None:
    _, _, controls, operation = case()
    with pytest.raises(OwnershipConflict):
        controls.bind(operation.model_copy(update={"owner_id": "foreign"}))
    for field in ("execution_deadline", "cleanup_deadline"):
        values = controls.window.model_dump()
        values[field] = values["hard_end"]
        with pytest.raises(ValidationError):
            OperationTimeWindow.model_validate(values)
