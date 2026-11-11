"""Actual loop preflight boundary; retain prefixes without replaying producers."""

from pathlib import Path
from typing import Any, cast

import pytest

from test_actor_round_admission import bounded_case
from lab_generate_skill.application.actor_generation import ActorDispatchFailure
from lab_generate_skill.application.actor_loop import ActorLoopFailure
from lab_generate_skill.domain.actor_budget_stop import ActorRoundBudgetStopped
from lab_generate_skill.domain.actor_execution_window import ActorGenerationWindow
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.trace_events import GenerationObserved, GenerationPlanned


@pytest.mark.parametrize("completed", [0, 1])
def test_preflight_deadline_preserves_completed_prefix_without_next_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, completed: int
) -> None:
    c, clock, _, request, runner = bounded_case(tmp_path, 500)
    c.loader.session.output = c.loader.session.output.model_copy(
        update={"text": '{"action":"click(\'2\')"}'}
    )
    validate = c.model.validate
    validations = 0

    def delayed(intent: Any, *, control: Any) -> None:
        nonlocal validations
        if validations == completed:
            clock.sleep(intent.execution_window.effective_preparation_seconds)
        validations += 1
        validate(intent, control=control)

    monkeypatch.setattr(c.model, "validate", delayed)
    with pytest.raises(ActorLoopFailure) as caught:
        runner.run(request)
    primary = caught.value.primary
    assert isinstance(primary, ActorRoundBudgetStopped)
    assert primary.known_unsent and primary.round_index == completed
    assert primary.stage == "preparation"
    dispatch = primary.__cause__
    assert isinstance(dispatch, ActorDispatchFailure)
    assert dispatch.phase == "preflight"
    assert isinstance(dispatch.primary, OperationStopped)
    assert dispatch.primary.reason_code == "DEADLINE_EXCEEDED"
    assert dispatch.acknowledged is dispatch.returned is dispatch.observed is None
    snapshot = caught.value.snapshot
    assert snapshot is not None
    view = snapshot.project()
    assert view.sealed is not None and view.sealed.stop_reason == "error"
    assert view.sealed.generations == view.sealed.interactions == completed
    assert view.intent is None
    assert all(turn.generation.status == "completed" for turn in view.turns)
    assert c.loader.session.calls == c.loop.browser.calls == completed
    assert caught.value.cleanup_errors == ()
    # A retained failure never creates a continuation opportunity.
    with pytest.raises(ActorLoopFailure):
        runner.run(request)
    assert c.loader.session.calls == c.loop.browser.calls == completed


@pytest.mark.parametrize(
    "fault",
    [
        "cancel",
        "engineering",
        "legacy_preflight",
        "commit_intent",
        "before_generate",
        "generate",
        "commit_result",
    ],
)
def test_other_dispatch_failures_keep_original_unknown_or_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c, clock, _, request, runner = bounded_case(tmp_path, 500)
    if fault == "legacy_preflight":
        request = request.model_copy(update={"generation_budgets": None})
    append = c.loop.journal.append

    def rejected_preflight(intent: Any, *, control: Any) -> None:
        if fault == "engineering":
            raise OSError("preflight storage unavailable")
        raise OperationStopped(
            "CANCELLED" if fault == "cancel" else "DEADLINE_EXCEEDED",
            intent.operation.operation_id,
        )

    def append_fault(event: Any, revision: Any, operation: Any) -> Any:
        if (fault == "commit_intent" and isinstance(event, GenerationPlanned)) or (
            fault == "commit_result" and isinstance(event, GenerationObserved)
        ):
            raise OperationStopped("DEADLINE_EXCEEDED", operation.operation_id)
        result = append(event, revision, operation)
        if fault == "before_generate" and isinstance(event, GenerationPlanned):
            clock.sleep(
                cast(
                    ActorGenerationWindow, event.intent.execution_window
                ).effective_preparation_seconds
            )
        return result

    def generate_fault(intent: Any, *, control: Any) -> Any:
        raise OperationStopped("DEADLINE_EXCEEDED", intent.operation.operation_id)

    if fault in ("cancel", "engineering", "legacy_preflight"):
        monkeypatch.setattr(c.model, "validate", rejected_preflight)
    elif fault == "generate":
        monkeypatch.setattr(c.model, "generate", generate_fault)
    else:
        monkeypatch.setattr(c.loop.journal, "append", append_fault)
    with pytest.raises(ActorLoopFailure) as caught:
        runner.run(request)
    primary = caught.value.primary
    assert isinstance(primary, ActorDispatchFailure)
    assert not isinstance(primary, ActorRoundBudgetStopped)
    expected_phase = (
        "preflight" if fault in ("cancel", "engineering", "legacy_preflight") else fault
    )
    assert primary.phase == expected_phase
    if fault == "engineering":
        assert isinstance(primary.primary, OSError)
    else:
        assert isinstance(primary.primary, OperationStopped)
        assert primary.primary.reason_code == (
            "CANCELLED" if fault == "cancel" else "DEADLINE_EXCEEDED"
        )
    assert c.loader.session.calls == (1 if fault == "commit_result" else 0)
    assert c.loop.browser.calls == 0
    if fault in ("before_generate", "generate", "commit_result"):
        snapshot = caught.value.snapshot
        assert snapshot is not None
        view = snapshot.project()
        assert view.intent is not None and view.sealed is None
