"""Leaf failure exits; synthetic components never claim browser process recovery."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation, BrowserTab
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.ports.lifecycle import OperationControl
from browsergym_fixtures import spec, operation, LoopbackAuthority
from evidence_control_fixtures import EvidenceFixtureStore
from test_core_contracts import reference
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "failed_names",
    [("task",), ("chat",), ("context",), ("browser",), ("driver",), ("task", "driver")],
)
def test_close_attempts_all_original_components_and_retains_failures(
    failed_names: tuple[str, ...],
) -> None:
    engine = BrowserGymEngine(
        spec(), LoopbackAuthority(), SystemClock(), NavigatePublicTask()
    )
    calls: list[str] = []
    fail = set(failed_names)

    class Item:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            calls.append(self.name)
            if self.name in fail:
                raise OSError(self.name)

        def teardown(self) -> None:
            self.close()

        def stop(self) -> None:
            self.close()

    engine.env = SimpleNamespace(
        **{name: Item(name) for name in ("task", "chat", "context", "browser")}
    )
    engine.driver = Item("driver")
    op = operation(engine.spec, "initial").cleanup(
        "close", now=datetime.now(timezone.utc), seconds=30
    )
    with pytest.raises(BaseExceptionGroup) as caught:
        engine.close(op, control=guard(30))
    assert calls == ["task", "chat", "context", "browser", "driver"]
    assert [str(error) for error in caught.value.exceptions] == list(failed_names)
    assert engine.state == "quarantined"
    fail.clear()
    calls.clear()
    engine.close(op, control=guard(30))
    assert calls == list(failed_names) and getattr(engine, "state") == "closed"
    calls.clear()
    engine.close(op, control=guard(30))
    assert calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "other"),
        ("owner_id", "other"),
        ("attempt_id", "other"),
        ("mode", "cleanup"),
    ],
)
def test_wrong_scope_or_phase_rejected_before_resources(field: str, value: str) -> None:
    engine = BrowserGymEngine(
        spec(), LoopbackAuthority(), SystemClock(), NavigatePublicTask()
    )
    op = operation(engine.spec, "start").model_copy(update={field: value})
    with pytest.raises((ValidationError, OwnershipConflict)):
        engine.start(op, control=guard(30))
    assert engine.env is None and engine.driver is None and engine.state == "new"


@pytest.mark.parametrize("failed_put", [1, 2])
def test_publication_failure_preserves_actual_readout_and_prevents_action_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_put: int
) -> None:
    frozen = spec()
    engine = BrowserGymEngine(
        frozen, LoopbackAuthority(), SystemClock(), NavigatePublicTask()
    )
    store = EvidenceFixtureStore(tmp_path)
    session = EvidenceBrowserSession(engine, store)
    session.observation_ref = reference("public", "observation/1")
    action = BrowserAction(
        action_id="save",
        protocol_id="browsergym-highlevel-v1",
        name="click",
        payload="click('a')",
    )
    op = operation(frozen, "save")
    observation = Observation(
        observation_id="after",
        task=frozen.task.identity,
        context_id=frozen.scope.context_id,
        attempt_id=frozen.scope.attempt_id,
        sequence=1,
        captured_at=datetime.now(timezone.utc),
        tabs=(BrowserTab(tab_id="tab", url=frozen.task.start_url, title="Saved"),),
        active_tab_id="tab",
        state="ready",
        text="Saved",
    )
    readout = BrowserReadout(
        scope=frozen.scope,
        operation=op,
        action=action,
        observation=observation,
        events=(),
        environment_reward=0.0,
        terminated=False,
        truncated=False,
        protocol_terminal=False,
    )
    calls: list[str] = []

    def step(
        action: BrowserAction, operation: OperationContext, *, control: OperationControl
    ) -> BrowserReadout:
        if engine.state == "quarantined":
            raise InvalidTransition("quarantined")
        calls.append(action.action_id)
        engine.last_readout = readout
        return readout

    monkeypatch.setattr(engine, "step", step)
    engine.state = "ready"
    saved_return = reference("private", "browser-step-return/1")
    puts: list[EvidenceMetadata] = []

    def fail(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        puts.append(metadata)
        if len(puts) == failed_put:
            raise OSError("evidence publication failed")
        return saved_return

    monkeypatch.setattr(store, "put", fail)
    with pytest.raises(OSError, match="publication"):
        session.step(action, op, control=guard(30))
    assert (
        engine.last_readout == readout
        and getattr(engine, "state") == "quarantined"
        and session.last_return_ref == (saved_return if failed_put == 2 else None)
    )
    with pytest.raises(InvalidTransition):
        session.step(action, op, control=guard(30))
    assert calls == ["save"] and len(puts) == failed_put
    assert session.last_return_ref == (saved_return if failed_put == 2 else None)
