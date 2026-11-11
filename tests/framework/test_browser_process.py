"""Map-required lifecycle seam: unique return, no replay, partial failure closure."""

from datetime import datetime, timezone
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from browsergym_fixtures import spec, operation, LoopbackAuthority
from browser_process_fixtures import case
from test_slurm_commands import guard


def action() -> BrowserAction:
    return BrowserAction(
        action_id="one",
        protocol_id="browsergym-highlevel-v1",
        name="fill",
        payload="fill('a','x')",
    )


def close(engine: BrowserGymEngine) -> None:
    op = operation(engine.spec, "original").cleanup(
        "close", now=datetime.now(timezone.utc), seconds=30
    )
    engine.close(op, control=guard(30))


@pytest.mark.parametrize("enabled", [True, False])
def test_original_observations_and_effects_remain_unique(
    monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    engine, collector, calls = case(monkeypatch, enabled=enabled)
    initial = engine.start(operation(engine.spec, "start"), control=guard())
    actual = engine.step(action(), operation(engine.spec, "step"), control=guard())
    assert initial.observation.sequence == 0 and actual.observation.sequence == 1
    assert calls == (
        [
            "attach",
            "navigate",
            "project",
            "observe",
            "before_action",
            "actual_action",
            "project",
            "observe",
        ]
        if enabled
        else ["navigate", "project", "actual_action", "project"]
    )
    assert collector.readouts == ([initial, actual] if enabled else [])
    assert engine.last_readout is actual
    before = list(calls)
    with pytest.raises(InvalidTransition):
        engine.step(action(), operation(engine.spec, "again"), control=guard())
    assert calls == before
    close(engine)
    close(engine)
    assert calls.count("collector_close") == int(enabled) and calls.count("driver") == 1


@pytest.mark.parametrize(
    "fault", ["attach", "observe", "before_action", "second_observe"]
)
def test_failed_collection_retains_actual_return_and_never_replays(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    engine, collector, calls = case(
        monkeypatch, fault if fault in ("attach", "observe") else ""
    )
    if fault in ("attach", "observe"):
        with pytest.raises(OSError):
            engine.start(operation(engine.spec, "start"), control=guard())
        assert ("navigate" in calls) == (fault == "observe")
        assert (engine.last_readout is not None) == (fault == "observe")
        assert engine.sequence == 0
    else:
        engine.start(operation(engine.spec, "start"), control=guard())
        collector.fault = "observe" if fault == "second_observe" else fault
        with pytest.raises(OSError):
            engine.step(action(), operation(engine.spec, "step"), control=guard())
        assert calls.count("actual_action") == int(fault == "second_observe")
        assert (engine.last_readout is not None) == (fault == "second_observe")
        assert engine.sequence == int(fault == "second_observe")
    assert engine.state == "quarantined"
    before = list(calls)
    with pytest.raises(InvalidTransition):
        engine.step(action(), operation(engine.spec, "again"), control=guard())
    assert calls == before
    close(engine)
    assert calls.count("collector_close") == 1 and calls.count("driver") == 1


def test_sealed_process_blocks_new_action_before_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, collector, calls = case(monkeypatch)
    engine.start(operation(engine.spec, "start"), control=guard())
    collector.sealed = True
    with pytest.raises(ValueError, match="sealed"):
        engine.step(action(), operation(engine.spec, "step"), control=guard())
    assert "actual_action" not in calls and engine.sequence == 0
    close(engine)


def test_failed_process_close_still_closes_browser_and_only_retries_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, collector, calls = case(monkeypatch)
    engine.start(operation(engine.spec, "start"), control=guard())
    collector.fault = "collector_close"
    with pytest.raises(BaseExceptionGroup) as caught:
        close(engine)
    assert [str(e) for e in caught.value.exceptions] == ["collector_close"]
    assert calls[-5:] == ["collector_close", "chat", "context", "browser", "driver"]
    assert engine.state == "quarantined"
    before = list(calls)
    collector.fault = ""
    close(engine)
    assert (
        calls == before + ["collector_close"] and getattr(engine, "state") == "closed"
    )


@pytest.mark.parametrize("invalid", ["", {}, [], 42, False, object()])
def test_incomplete_collector_rejected_before_browser(invalid: Any) -> None:
    with pytest.raises(TypeError):
        BrowserGymEngine(
            spec(),
            LoopbackAuthority(),
            SystemClock(),
            NavigatePublicTask(),
            process_collector=invalid,
        )


def test_wrong_scope_and_cancel_before_start_do_not_attach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, collector, calls = case(monkeypatch)
    with pytest.raises(OwnershipConflict):
        engine.start(
            operation(engine.spec, "start").model_copy(update={"attempt_id": "wrong"}),
            control=guard(),
        )
    assert calls == [] and collector.readouts == []

    class Stopped:
        def checkpoint(self) -> float:
            raise TimeoutError("cancelled")

        def wait(self, seconds: float) -> None:
            raise TimeoutError("cancelled")

    with pytest.raises(TimeoutError):
        engine.start(operation(engine.spec, "start"), control=Stopped())
    assert calls == [] and engine.env is None
