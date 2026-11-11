"""Exact owned pidfds: normal, native stop, stale/invalid input and cleanup faults."""

from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.processes import worker_processes as module
from lab_generate_skill.adapters.browsergym.step_processes import (
    PinnedBrowserProcesses,
    pin_browser_processes,
)
from lab_generate_skill.adapters.browsergym.step import BrowserStepState
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from browser_resource_fixtures import resource_case
from browser_step_fixtures import unit_started
from generator_worker_fixtures import unit_guard


class Control:
    def __init__(self, limit: int = 30) -> None:
        self.waits: list[float] = []
        self.limit = limit
        self.cancelled = False

    def checkpoint(self) -> float:
        if self.cancelled or len(self.waits) >= self.limit:
            raise TimeoutError("bounded cleanup stop")
        return 1.0

    def wait(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.checkpoint()


class Harness:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        c = resource_case(tmp_path, monkeypatch)
        self.guard = unit_guard(c.spec.slurm.parent.writer, Control())
        state = BrowserStepState(
            launcher=self.guard.controller.model_copy(
                update={"process_id": self.guard.controller.process_id + 10000002}
            )
        )
        unit_started(c.spec, state, self.guard, c.evidence, Control())
        assert state.target is not None
        self.target = state.target
        self.exit: set[int] = set()
        self.kills: list[int] = []
        self.closed: list[int] = []
        self.pin_calls: list[int] = []
        self.auto_exit = True
        self.auto_reap = True
        self.fail_pin = False
        self.fail_signal: BaseException | None = None
        self.fail_close = False

        @contextmanager
        def pin(expected: Any, control: OperationControl) -> Iterator[int]:
            control.checkpoint()
            fd = 100 if expected == self.guard.worker else 101
            self.pin_calls.append(fd)
            if self.fail_pin and fd == 101:
                raise OSError("second pin failed")
            try:
                yield fd
            finally:
                self.closed.append(fd)
                if self.fail_close:
                    raise OSError("descriptor close failed")

        def kill(fd: int) -> None:
            self.kills.append(fd)
            if self.fail_signal is not None:
                raise self.fail_signal
            if self.auto_exit:
                self.exit.add(fd)
                if fd == 100 and self.auto_reap:
                    self.exit.add(101)

        monkeypatch.setattr(module, "pinned_owner", pin)
        monkeypatch.setattr(module, "ended", lambda fd: fd in self.exit)
        monkeypatch.setattr(module, "kill_pidfd", kill)

    def pin(self) -> PinnedBrowserProcesses:
        return pin_browser_processes(self.guard, self.target, Control())


@pytest.fixture
def h(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(tmp_path, monkeypatch)


@pytest.mark.parametrize("already_exited", [False, True])
def test_exact_worker_stop_and_repeat_without_new_signal(
    h: Harness, already_exited: bool
) -> None:
    handle = h.pin()
    if already_exited:
        h.exit.update({100, 101})
    facts = handle.stop(Control())
    assert facts.worker_exit_observed and facts.supervisor_exit_observed
    assert facts.worker_signal_requested is (not already_exited)
    assert not facts.supervisor_signal_requested
    assert h.kills == ([] if already_exited else [100])
    assert handle.stop(Control()) == facts
    handle.close()
    handle.close()
    assert h.closed == [101, 100]
    with pytest.raises(OwnershipConflict):
        handle.stop(Control())


def test_stuck_original_supervisor_has_bounded_fallback(h: Harness) -> None:
    h.auto_reap = False
    handle = h.pin()
    control = Control()
    facts = handle.stop(control)
    assert h.kills == [100, 101] and len(control.waits) == 10
    assert facts.worker_exit_observed and facts.supervisor_exit_observed
    assert facts.supervisor_signal_requested
    handle.close()


def test_stop_deadline_retains_requested_signal_without_claiming_exit(
    h: Harness,
) -> None:
    h.auto_exit = False
    handle = h.pin()
    with pytest.raises(TimeoutError):
        handle.stop(Control(limit=1))
    assert h.kills == [100] and handle.facts.worker_signal_requested
    assert (
        not handle.facts.worker_exit_observed
        and not handle.facts.supervisor_exit_observed
    )
    handle.close()


@pytest.mark.parametrize(
    "failure", [PermissionError("signal denied"), OSError("signal unknown")]
)
def test_signal_error_is_preserved_and_not_reported_stopped(
    h: Harness, failure: BaseException
) -> None:
    h.fail_signal = failure
    handle = h.pin()
    with pytest.raises(BaseException) as caught:
        handle.stop(Control())
    assert caught.value is failure and handle.facts.worker_signal_requested
    assert not handle.facts.worker_exit_observed
    handle.close()


def test_missing_process_error_requires_independent_exit_observation(
    h: Harness,
) -> None:
    h.fail_signal = ProcessLookupError("not a positive exit observation")
    handle = h.pin()
    with pytest.raises(TimeoutError):
        handle.stop(Control(limit=1))
    assert not handle.facts.worker_exit_observed
    handle.close()


def test_second_pin_failure_closes_first_original_handle(h: Harness) -> None:
    h.fail_pin = True
    with pytest.raises(OSError, match="second pin"):
        h.pin()
    assert h.pin_calls == [100, 101] and h.closed == [100] and not h.kills


def test_foreign_context_and_cancelled_guard_have_no_signals(h: Harness) -> None:
    handle = h.pin()
    original = handle._context
    handle._context = (original[0], -1)
    with pytest.raises(OwnershipConflict):
        handle.stop(Control())
    handle._context = original
    control = Control()
    control.cancelled = True
    with pytest.raises(TimeoutError):
        handle.stop(control)
    assert not h.kills
    handle.close()


def test_close_failure_still_attempts_both_descriptors(h: Harness) -> None:
    handle = h.pin()
    h.fail_close = True
    with pytest.raises(OSError):
        handle.close()
    assert h.closed == [101, 100]
    with pytest.raises(OwnershipConflict):
        handle.stop(Control())


@pytest.mark.parametrize("change", ["worker", "gpu", "launcher"])
def test_foreign_guard_or_target_rejected_before_pin(h: Harness, change: str) -> None:
    target = h.target
    if change == "gpu":
        target = target.model_copy(update={"resources": "single_gpu"})
    elif change == "launcher":
        target = target.model_copy(update={"launcher": h.guard.supervisor})
    else:
        target = target.model_copy(
            update={
                "worker": target.worker.model_copy(
                    update={
                        "writer": h.guard.worker.model_copy(
                            update={"process_id": h.guard.worker.process_id + 10}
                        )
                    }
                )
            }
        )
    with pytest.raises(ValueError):
        pin_browser_processes(h.guard, target, Control())
    assert not h.pin_calls and not h.kills


@pytest.mark.parametrize("value", [None, {}, [], True])
def test_empty_or_wrong_guard_rejected_before_pinning(h: Harness, value: Any) -> None:
    with pytest.raises(ValueError):
        pin_browser_processes(value, h.target, Control())
    assert not h.pin_calls and not h.kills


def test_shared_facts_keep_original_browser_canonical_field_order(h: Harness) -> None:
    handle = h.pin()
    assert list(handle.facts.model_dump()) == [
        "schema_version",
        "target",
        "guard",
        "worker_signal_requested",
        "supervisor_signal_requested",
        "worker_exit_observed",
        "supervisor_exit_observed",
    ]
    handle.close()
