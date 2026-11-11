"""Physical I/O identities retain opaque original control and frozen ceilings."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.runtime.evidence_operations import EvidenceOperations
from evidence_session_fixtures import binding
from test_lifecycle import ManualClock


class OpaqueControl:
    def __init__(self, clock: ManualClock, seconds: float = 10) -> None:
        self.clock, self.expires = clock, clock.elapsed + seconds
        self.stopped = False
        self.poll_cost = 0.0
        self.calls = 0

    @property
    def context(self) -> OperationContext:
        raise AssertionError("Control internals are not part of its port")

    def checkpoint(self) -> float:
        self.calls += 1
        self.clock.sleep(self.poll_cost)
        if self.stopped or self.clock.elapsed >= self.expires:
            raise OperationStopped(
                "CANCELLED" if self.stopped else "DEADLINE_EXCEEDED", "original"
            )
        return self.expires - self.clock.elapsed

    def wait(self, seconds: float) -> None:
        self.clock.sleep(min(seconds, self.checkpoint()))
        self.checkpoint()


def test_same_caller_deadline_across_multiple_physical_exchanges() -> None:
    clock = ManualClock()
    original = OpaqueControl(clock)
    operations = EvidenceOperations(binding(), clock, max_io_seconds=20)
    first = operations.prepare("first", original)
    clock.sleep(2)
    second = operations.prepare("second", original)
    assert first.operation.deadline == second.operation.deadline
    assert first.operation.operation_id != second.operation.operation_id
    assert first.control.checkpoint() == second.control.checkpoint() == 8
    assert first.operation.run_id == binding().owner.run_id
    assert (
        first.operation.attempt_id is None and first.operation.cancellation_ref is None
    )
    assert first.bind(first.operation) is first.control
    original.stopped = True
    for active in (first, second):
        with pytest.raises(OperationStopped, match="CANCELLED"):
            active.control.checkpoint()


def test_physical_ceiling_shortens_and_wall_rollback_never_extends() -> None:
    clock = ManualClock()
    original = OpaqueControl(clock, 50)
    active = EvidenceOperations(binding(), clock, max_io_seconds=4).prepare(
        "first", original
    )
    clock.sleep(2)
    clock.wall -= timedelta(hours=1)
    assert active.control.checkpoint() == 2
    clock.sleep(2)
    calls = original.calls
    with pytest.raises(OperationStopped):
        active.control.checkpoint()
    assert (
        original.calls == calls
    )  # already-expired ceiling avoids another provider read


def test_slow_original_poll_is_counted_not_added_back() -> None:
    clock = ManualClock()
    original = OpaqueControl(clock)
    original.poll_cost = 1
    started = clock.utcnow()
    active = EvidenceOperations(binding(), clock, max_io_seconds=20).prepare(
        "first", original
    )
    assert active.operation.deadline == started + timedelta(seconds=9)
    assert active.control.checkpoint() == 6


def test_rollback_during_first_poll_cannot_extend_physical_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = ManualClock()
    original = OpaqueControl(clock, 50)
    checkpoint = original.checkpoint
    first = True

    def poll() -> float:
        nonlocal first
        if first:
            first = False
            clock.sleep(2)
            clock.wall -= timedelta(hours=1)
        return checkpoint()

    monkeypatch.setattr(original, "checkpoint", poll)
    active = EvidenceOperations(binding(), clock, max_io_seconds=4).prepare(
        "first", original
    )
    assert active.control.checkpoint() == 2
    clock.sleep(2)
    with pytest.raises(OperationStopped, match="DEADLINE_EXCEEDED"):
        active.control.checkpoint()


@pytest.mark.parametrize("cost", [4, 5])
def test_first_poll_exhaustion_rejects_even_after_wall_rollback(
    cost: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = ManualClock()
    original = OpaqueControl(clock, 50)
    checkpoint = original.checkpoint

    def poll() -> float:
        clock.sleep(cost)
        clock.wall -= timedelta(hours=1)
        return checkpoint()

    monkeypatch.setattr(original, "checkpoint", poll)
    with pytest.raises(OperationStopped, match="DEADLINE_EXCEEDED"):
        EvidenceOperations(binding(), clock, max_io_seconds=4).prepare(
            "first", original
        )
    assert original.calls == 1


@pytest.mark.parametrize("bad", [None, False, "0", float("nan"), float("inf"), 10**400])
def test_bad_initial_monotonic_clock_rejects_before_caller_poll(
    bad: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = ManualClock()
    original = OpaqueControl(clock)
    monkeypatch.setattr(clock, "monotonic", lambda: bad)
    with pytest.raises(ValueError):
        EvidenceOperations(binding(), clock, max_io_seconds=4).prepare(
            "first", original
        )
    assert original.calls == 0


def test_backward_monotonic_clock_is_rejected() -> None:
    clock = ManualClock()
    active = EvidenceOperations(binding(), clock, max_io_seconds=4).prepare(
        "first", OpaqueControl(clock)
    )
    clock.elapsed = -1
    with pytest.raises(ValueError, match="elapsed"):
        active.control.checkpoint()


def test_original_expiry_and_wait_are_preserved() -> None:
    clock = ManualClock()
    original = OpaqueControl(clock, 3)
    active = EvidenceOperations(binding(), clock, max_io_seconds=20).prepare(
        "first", original
    )
    active.control.wait(1)
    assert active.control.checkpoint() == 2
    with pytest.raises(OperationStopped):
        active.control.wait(100)
    assert clock.elapsed == 3


def test_duplicate_id_and_changed_context_cannot_restart_deadline() -> None:
    clock = ManualClock()
    factory = EvidenceOperations(binding(), clock, max_io_seconds=10)
    first = factory.prepare("first", OpaqueControl(clock))
    clock.sleep(1)
    with pytest.raises(OwnershipConflict):
        factory.prepare("first", OpaqueControl(clock, 100))
    with pytest.raises(OwnershipConflict):
        first.bind(
            first.operation.model_copy(
                update={"deadline": first.operation.deadline + timedelta(seconds=1)}
            )
        )


@pytest.mark.parametrize(
    "bad", [0, -1, False, float("nan"), float("inf"), 86401, "1", None]
)
def test_invalid_physical_ceiling_rejected(bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        EvidenceOperations(binding(), ManualClock(), max_io_seconds=cast(float, bad))


@pytest.mark.parametrize("bad", ["", "../x", "x" * 257, None, False])
def test_invalid_exchange_never_polls_control(bad: object) -> None:
    clock = ManualClock()
    original = OpaqueControl(clock)
    factory = EvidenceOperations(binding(), clock, max_io_seconds=10)
    with pytest.raises(ValidationError):
        factory.prepare(cast(str, bad), original)
    assert original.calls == 0


@pytest.mark.parametrize("bad", [0, -1, False, float("nan"), float("inf"), None])
def test_invalid_original_remaining_is_not_guessed(
    bad: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = ManualClock()
    original = OpaqueControl(clock)
    monkeypatch.setattr(original, "checkpoint", lambda: bad)
    with pytest.raises((TypeError, ValueError)):
        EvidenceOperations(binding(), clock, max_io_seconds=10).prepare(
            "first", original
        )


@pytest.mark.parametrize("bad", [-1, False, float("nan"), float("inf"), None])
def test_invalid_wait_never_sleeps(bad: object) -> None:
    clock = ManualClock()
    active = EvidenceOperations(binding(), clock, max_io_seconds=10).prepare(
        "first", OpaqueControl(clock)
    )
    with pytest.raises((TypeError, ValueError)):
        active.control.wait(cast(float, bad))
    assert clock.elapsed == 0


def test_competing_prepare_keeps_one_original_identity() -> None:
    clock = ManualClock()
    factory = EvidenceOperations(binding(), clock, max_io_seconds=10)

    def prepare(index: int) -> bool:
        try:
            factory.prepare("same", OpaqueControl(clock))
        except OwnershipConflict:
            return False
        return True

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(prepare, range(8))) == 1
