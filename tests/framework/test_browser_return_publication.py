"""Original action expiry cannot erase a returned readout or renew a result window."""

from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest

from browsergym_fixtures import LoopbackAuthority, spec
from evidence_control_fixtures import EvidenceFixtureStore
from test_core_contracts import reference
from test_lifecycle import CancelSwitch, ManualClock
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
from lab_generate_skill.adapters.browsergym.return_publication import (
    BrowserReturnPublication,
)
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    CancellationRef,
    OperationContext,
)
from lab_generate_skill.domain.observation import BrowserTab, Observation
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards


def allocation() -> AllocationToken:
    return AllocationToken(
        allocation_id="execution.browser",
        owner=spec().scope.owner,
        scope="attempt",
        attempt_id=spec().scope.attempt_id,
        resource_kind="browser",
        expected_resource_id="original-browser",
        provider_id="fixed-browser-worker",
        provider_version="1",
        recovery_ref=reference("private", "recovery-plan/1"),
    )


def action_operation(clock: ManualClock) -> OperationContext:
    token = allocation()
    return OperationContext(
        operation_id="original-step",
        run_id=token.owner.run_id,
        owner_id=token.owner.owner_id,
        attempt_id=token.attempt_id,
        allocation_id=token.allocation_id,
        recovery_ref=token.recovery_ref,
        cancellation_ref=CancellationRef(
            channel_id="cancel",
            run_id=token.owner.run_id,
            owner_id=token.owner.owner_id,
        ),
        deadline=clock.utcnow() + timedelta(seconds=10),
    )


@pytest.mark.parametrize("independent", [False, True])
@pytest.mark.parametrize("cancelled", [False, True])
def test_actual_return_survives_action_expiry_or_cancel_without_new_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, independent: bool, cancelled: bool
) -> None:
    clock, cancel = ManualClock(), CancelSwitch()
    controls = OperationGuards(clock, cancel)
    op = action_operation(clock)
    frozen = spec()
    engine = BrowserGymEngine(frozen, LoopbackAuthority(), clock, NavigatePublicTask())
    store = EvidenceFixtureStore(tmp_path)
    session = EvidenceBrowserSession(
        engine,
        store,
        return_publication=(
            BrowserReturnPublication(allocation(), controls, clock, 60)
            if independent
            else None
        ),
    )
    session.observation_ref = reference("public", "observation/1")
    action = BrowserAction(
        action_id="click-once",
        protocol_id="browsergym-highlevel-v1",
        name="click",
        payload="click('a')",
    )
    observed = Observation(
        observation_id="after",
        task=frozen.task.identity,
        context_id=frozen.scope.context_id,
        attempt_id=frozen.scope.attempt_id,
        sequence=1,
        captured_at=clock.utcnow(),
        tabs=(BrowserTab(tab_id="tab", url=frozen.task.start_url, title="After"),),
        active_tab_id="tab",
        state="ready",
        text="Actual returned page",
    )
    readout = BrowserReadout(
        scope=frozen.scope,
        operation=op,
        action=action,
        observation=observed,
        events=(),
        environment_reward=0.0,
        terminated=False,
        truncated=False,
        protocol_terminal=False,
    )
    calls = []

    def step(
        action: BrowserAction, operation: OperationContext, *, control: OperationControl
    ) -> BrowserReadout:
        control.checkpoint()
        assert operation == op
        calls.append(action.action_id)
        engine.last_readout = readout
        clock.sleep(10)
        cancel.cancelled = cancelled
        return readout

    monkeypatch.setattr(engine, "step", step)
    engine.state = "ready"
    original_control = controls.bind(op)
    if independent:
        result = session.step(action, op, control=original_control)
        assert result.operation == op and result.before_observation_ref == reference(
            "public", "observation/1"
        )
        assert result.return_ref is not None
        assert (
            BrowserReadout.model_validate_json(store.read(result.return_ref)) == readout
        )
        assert (
            Observation.model_validate_json(store.read(result.observation_ref))
            == observed
        )
        assert session.last_return_ref == result.return_ref
    else:
        # Reproduce the original interface fault: a returned native fact is
        # followed by publication under the exhausted/cancelled action control.
        with pytest.raises(OperationStopped):
            session.step(action, op, control=original_control)
        assert session.last_return_ref is None
        with pytest.raises(InvalidTransition):
            session.step(action, op, control=original_control)
    assert calls == ["click-once"] and engine.last_readout == readout
    with pytest.raises(OperationStopped):
        original_control.checkpoint()


def test_publication_window_is_consumed_once_and_never_extends_original_result_deadline() -> (
    None
):
    clock, cancel = ManualClock(), CancelSwitch()
    controls = OperationGuards(clock, cancel)
    op = action_operation(clock)
    publication = BrowserReturnPublication(allocation(), controls, clock, 60)
    clock.sleep(69)
    bound = publication.bind(op)
    assert bound.checkpoint() == 1
    with pytest.raises(OwnershipConflict):
        publication.bind(op)
    clock.sleep(1)
    with pytest.raises(OperationStopped):
        bound.checkpoint()


def test_late_return_cannot_create_a_fresh_cleanup_window() -> None:
    clock = ManualClock()
    op = action_operation(clock)
    publication = BrowserReturnPublication(
        allocation(), OperationGuards(clock, CancelSwitch()), clock, 60
    )
    clock.sleep(70)
    with pytest.raises(OperationStopped):
        publication.bind(op)


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "other"),
        ("owner_id", "other"),
        ("attempt_id", "other"),
        ("allocation_id", "other"),
        ("recovery_ref", reference("private", "other/1")),
        ("mode", "cleanup"),
    ],
)
def test_foreign_or_cleanup_action_cannot_publish_as_original(
    field: str, value: object
) -> None:
    clock = ManualClock()
    publication = BrowserReturnPublication(
        allocation(), OperationGuards(clock, CancelSwitch()), clock, 60
    )
    changed = action_operation(clock).model_copy(update={field: value})
    if field in ("run_id", "owner_id"):
        changed = changed.model_copy(update={"cancellation_ref": None})
    if field == "mode":
        changed = changed.model_copy(update={"parent_operation_id": "original-parent"})
    with pytest.raises(OwnershipConflict):
        publication.bind(changed)


@pytest.mark.parametrize("seconds", [True, 0, -1, 61, 1.0, None, "60"])
def test_invalid_result_budget_is_rejected_before_publication(seconds: object) -> None:
    clock = ManualClock()
    with pytest.raises(ValueError):
        BrowserReturnPublication(
            allocation(),
            OperationGuards(clock, CancelSwitch()),
            clock,
            cast(int, seconds),
        )
