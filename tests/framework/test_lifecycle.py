"""Operation stop/cleanup invariants, including clock rollback and live cancel."""

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.lifecycle import CancellationRef, OperationContext
from lab_generate_skill.runtime.lifecycle import OperationGuards


class ManualClock:
    def __init__(self) -> None:
        self.wall = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.elapsed = 0.0

    def utcnow(self) -> datetime:
        return self.wall

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.elapsed += seconds
        self.wall += timedelta(seconds=seconds)


class CancelSwitch:
    def __init__(self) -> None:
        self.cancelled = False

    def is_cancelled(self, reference: CancellationRef) -> bool:
        return self.cancelled


def operation(clock: ManualClock) -> OperationContext:
    return OperationContext(
        operation_id="prepare",
        run_id="run",
        owner_id="owner",
        deadline=clock.utcnow() + timedelta(seconds=10),
        cancellation_ref=CancellationRef(
            channel_id="control", run_id="run", owner_id="owner"
        ),
    )


def test_deadline_round_trip_and_naive_clock_rejected() -> None:
    op = operation(ManualClock())
    assert OperationContext.model_validate_json(op.model_dump_json()) == op
    data = op.model_dump()
    data["deadline"] = datetime(2026, 1, 1)
    with pytest.raises(ValidationError):
        OperationContext.model_validate(data)


def test_cancellation_is_live_after_guard_binding() -> None:
    clock, cancel = ManualClock(), CancelSwitch()
    guard = OperationGuards(clock, cancel).bind(operation(clock))
    assert guard.checkpoint() == 10
    cancel.cancelled = True
    with pytest.raises(OperationStopped) as stopped:
        guard.checkpoint()
    assert stopped.value.reason_code == "CANCELLED"


def test_wall_clock_rollback_does_not_extend_rebound_operation() -> None:
    clock, cancel = ManualClock(), CancelSwitch()
    controls = OperationGuards(clock, cancel)
    op = operation(clock)
    first = controls.bind(op)
    clock.elapsed = 11
    clock.wall -= timedelta(days=1)
    assert controls.bind(op) is first
    with pytest.raises(OperationStopped) as stopped:
        controls.bind(op).checkpoint()
    assert stopped.value.reason_code == "DEADLINE_EXCEEDED"


def test_same_operation_id_cannot_gain_new_deadline() -> None:
    clock, cancel = ManualClock(), CancelSwitch()
    controls = OperationGuards(clock, cancel)
    original = operation(clock)
    controls.bind(original)
    data = original.model_dump()
    data["deadline"] = original.deadline + timedelta(hours=1)
    with pytest.raises(OwnershipConflict):
        controls.bind(OperationContext.model_validate(data))


def test_expired_cancelled_execution_still_gets_independent_cleanup() -> None:
    clock, cancel = ManualClock(), CancelSwitch()
    controls = OperationGuards(clock, cancel)
    op = operation(clock)
    controls.bind(op)
    clock.sleep(15)
    cancel.cancelled = True
    cleanup = op.cleanup("cleanup", now=clock.utcnow(), seconds=3)
    assert cleanup.parent_operation_id == op.operation_id
    assert cleanup.cancellation_ref is None
    assert cleanup.owner_id == op.owner_id
    guard = controls.bind(cleanup)
    assert guard.checkpoint() == 3
    with pytest.raises(OperationStopped):
        guard.wait(10)
    assert clock.elapsed == 18


@pytest.mark.parametrize("seconds", [0.0, -1.0, float("nan"), float("inf")])
def test_cleanup_requires_a_finite_positive_budget(seconds: float) -> None:
    clock = ManualClock()
    with pytest.raises(ValueError):
        operation(clock).cleanup("cleanup", now=clock.utcnow(), seconds=seconds)


def test_foreign_cancellation_channel_is_rejected() -> None:
    data = operation(ManualClock()).model_dump()
    data["cancellation_ref"] = CancellationRef(
        channel_id="control", run_id="other", owner_id="owner"
    )
    with pytest.raises(ValidationError):
        OperationContext.model_validate(data)


@pytest.mark.parametrize("seconds", [0.0, 0.001, 3.0, 9.999])
def test_wait_valid_boundaries_preserve_remaining_budget(seconds: float) -> None:
    clock = ManualClock()
    guard = OperationGuards(clock, CancelSwitch()).bind(operation(clock))
    guard.wait(seconds)
    assert clock.elapsed == seconds
    assert guard.checkpoint() == pytest.approx(10 - seconds)


@pytest.mark.parametrize("seconds", [10.0, 10.001, 1e100])
def test_wait_at_or_over_deadline_stops_without_oversleep(seconds: float) -> None:
    clock = ManualClock()
    guard = OperationGuards(clock, CancelSwitch()).bind(operation(clock))
    with pytest.raises(OperationStopped) as stopped:
        guard.wait(seconds)
    assert stopped.value.reason_code == "DEADLINE_EXCEEDED"
    assert clock.elapsed == 10


@pytest.mark.parametrize(
    "seconds", [True, False, -1.0, float("nan"), float("inf"), -float("inf"), 10**400]
)
def test_invalid_numeric_wait_is_rejected_before_sleep(seconds: object) -> None:
    clock = ManualClock()
    guard = OperationGuards(clock, CancelSwitch()).bind(operation(clock))
    with pytest.raises(ValueError):
        guard.wait(cast(float, seconds))
    assert clock.elapsed == 0
    assert guard.checkpoint() == 10


@pytest.mark.parametrize("seconds", [None, "", "1", [], {}])
def test_wrong_wait_type_is_rejected_before_sleep(seconds: object) -> None:
    clock = ManualClock()
    guard = OperationGuards(clock, CancelSwitch()).bind(operation(clock))
    with pytest.raises(TypeError):
        guard.wait(cast(float, seconds))
    assert clock.elapsed == 0


@pytest.mark.parametrize("seconds", [True, False, -float("inf"), 1e100, 10**400])
def test_cleanup_unrepresentable_or_invalid_budget(seconds: object) -> None:
    clock = ManualClock()
    op = operation(clock)
    with pytest.raises(ValueError):
        op.cleanup("cleanup", now=clock.utcnow(), seconds=cast(float, seconds))
    assert op.mode == "execute"
    assert op.deadline == clock.utcnow() + timedelta(seconds=10)


@pytest.mark.parametrize("seconds", [None, "", "1", [], {}])
def test_cleanup_wrong_duration_type(seconds: object) -> None:
    clock = ManualClock()
    with pytest.raises(TypeError):
        operation(clock).cleanup(
            "cleanup", now=clock.utcnow(), seconds=cast(float, seconds)
        )


def test_cleanup_overflow_at_calendar_limit_is_classified() -> None:
    with pytest.raises(ValueError):
        operation(ManualClock()).cleanup(
            "cleanup", now=datetime.max.replace(tzinfo=timezone.utc), seconds=1
        )


@pytest.mark.parametrize("invalid_clock", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_monotonic_clock_fails_closed_after_binding(
    invalid_clock: float,
) -> None:
    clock = ManualClock()
    guard = OperationGuards(clock, CancelSwitch()).bind(operation(clock))
    clock.elapsed = invalid_clock
    with pytest.raises(ValueError, match="clock"):
        guard.checkpoint()


def test_cancelled_wait_has_no_sleep_side_effect() -> None:
    clock, cancel = ManualClock(), CancelSwitch()
    guard = OperationGuards(clock, cancel).bind(operation(clock))
    cancel.cancelled = True
    with pytest.raises(OperationStopped) as stopped:
        guard.wait(1)
    assert stopped.value.reason_code == "CANCELLED"
    assert clock.elapsed == 0


def test_forward_wall_clock_jump_stops_even_before_monotonic_expiry() -> None:
    clock = ManualClock()
    guard = OperationGuards(clock, CancelSwitch()).bind(operation(clock))
    clock.wall += timedelta(hours=1)
    with pytest.raises(OperationStopped):
        guard.checkpoint()
    assert clock.elapsed == 0


@pytest.mark.parametrize(
    "invalid", [None, True, "1", 10**400, float("nan"), float("inf"), -float("inf")]
)
@pytest.mark.parametrize("after_binding", [False, True])
def test_bad_monotonic_provider_values_are_rejected_at_both_boundaries(
    invalid: object,
    after_binding: bool,
) -> None:
    clock = ManualClock()
    controls = OperationGuards(clock, CancelSwitch())
    op = operation(clock)
    if after_binding:
        guard = controls.bind(op)
        clock.elapsed = cast(float, invalid)
        with pytest.raises(ValueError, match="clock"):
            guard.checkpoint()
    else:
        clock.elapsed = cast(float, invalid)
        with pytest.raises(ValueError, match="clock"):
            controls.bind(op)


@pytest.mark.parametrize("after_binding", [False, True])
def test_naive_wall_clock_is_rejected_at_both_boundaries(after_binding: bool) -> None:
    clock = ManualClock()
    controls = OperationGuards(clock, CancelSwitch())
    op = operation(clock)
    if after_binding:
        guard = controls.bind(op)
        clock.wall = clock.wall.replace(tzinfo=None)
        with pytest.raises(ValueError, match="clock"):
            guard.checkpoint()
    else:
        clock.wall = clock.wall.replace(tzinfo=None)
        with pytest.raises(ValueError, match="clock"):
            controls.bind(op)


@pytest.mark.parametrize("seconds", [1, 0.000001, 60.0])
def test_legal_cleanup_duration_keeps_original_context_and_binding(
    seconds: float,
) -> None:
    clock = ManualClock()
    op = operation(clock)
    prior = op.model_dump_json()
    cleaned = op.cleanup("cleanup", now=clock.utcnow(), seconds=seconds)
    assert cleaned.deadline == clock.utcnow() + timedelta(seconds=seconds)
    assert cleaned.parent_operation_id == op.operation_id
    assert cleaned.run_id == op.run_id
    assert cleaned.owner_id == op.owner_id
    assert op.model_dump_json() == prior
