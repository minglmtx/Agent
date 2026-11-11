"""Real CAS/trace transactions and synthetic model facts; no inference permission."""

from datetime import datetime, timezone
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.actor_generation import (
    execute_actor_generation,
    ActorDispatchFailure,
)
from lab_generate_skill.application.browser_action import execute_browser_action
from lab_generate_skill.domain.actor_dispatch import ActorDispatch
from lab_generate_skill.domain.actor_generation import ActorGeneration
from lab_generate_skill.domain.browser_dispatch import BrowserDispatch
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.trace_events import (
    GenerationIntent,
    GenerationPlanned,
    GenerationObserved,
    ActionPlanned,
    InteractionObserved,
    TraceProgressEvent,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.ports.lifecycle import OperationControl
from trace_journal_fixtures import fixture, LiveTraceFixture
from test_run_journal import command
from test_browser_action import Browser, Checkpoints, Controls


class Model:
    def __init__(
        self, journal: FileTraceJournal, request: ActorDispatch, result: ActorGeneration
    ) -> None:
        self.journal, self.request, self.result = journal, request, result
        self.calls = 0
        self.preflight_error: BaseException | None = None
        self.failure: BaseException | None = None
        self.control: OperationControl | None = None

    def validate(self, intent: GenerationIntent, *, control: OperationControl) -> None:
        assert intent == self.request.intent.intent
        if self.preflight_error is not None:
            raise self.preflight_error

    def generate(
        self, intent: GenerationIntent, *, control: OperationControl
    ) -> ActorGeneration:
        snapshot = self.journal.read(command("inspect-generation", attempt="attempt"))
        assert snapshot.events[-1] == self.request.intent
        assert intent == self.request.intent.intent
        self.calls += 1
        self.control = control
        if self.failure is not None:
            raise self.failure
        return self.result


def prepared(
    root: Path, outcome: str = "returned"
) -> tuple[LiveTraceFixture, FileTraceJournal, ActorDispatch, Model]:
    data = fixture(root, outcomes=(outcome,))
    journal = data.journal()
    journal.create(data.plan, command("create", attempt="attempt"))
    intent, result = data.events()[:2]
    assert isinstance(intent, GenerationPlanned) and isinstance(
        result, GenerationObserved
    )
    request = ActorDispatch(
        intent=intent,
        expected_revision=0,
        result_operation=intent.intent.operation.cleanup(
            "record-generation", now=datetime.now(timezone.utc), seconds=60
        ),
    )
    return data, journal, request, Model(journal, request, result.generation)


@pytest.mark.parametrize(
    "outcome,status",
    [
        ("returned", "completed"),
        ("failed", "failed"),
        ("generation_unknown", "uncertain"),
    ],
)
def test_actual_outcome_persisted_and_repeated_call_never_sends(
    tmp_path: Path, outcome: str, status: str
) -> None:
    _, journal, request, model = prepared(tmp_path, outcome)
    after = execute_actor_generation(request, journal, model, journal.controls)
    assert after.revision == 2 and model.calls == 1
    last = after.events[-1]
    assert isinstance(last, GenerationObserved) and last.generation.status == status
    assert after.project().interactions == 0
    assert after.project().halted == (status != "completed")
    assert journal.read(command("read-result", attempt="attempt")) == after
    with pytest.raises(ActorDispatchFailure) as caught:
        execute_actor_generation(request, journal, model, journal.controls)
    assert isinstance(caught.value.primary, DispatchAlreadyCommitted)
    assert model.calls == 1


def test_generation_then_original_action_uses_same_observation_and_two_counts(
    tmp_path: Path,
) -> None:
    data, journal, request, model = prepared(tmp_path)
    generated = execute_actor_generation(request, journal, model, journal.controls)
    intent, observed = data.events()[2:4]
    assert isinstance(intent, ActionPlanned) and isinstance(
        observed, InteractionObserved
    )
    assert observed.interaction.result is not None
    dispatch = BrowserDispatch(
        intent=intent,
        expected_revision=generated.revision,
        result_operation=intent.execution_operation.cleanup(
            "record-browser", now=datetime.now(timezone.utc), seconds=60
        ),
    )
    browser = Browser(journal, dispatch, observed.interaction.result)
    after = execute_browser_action(dispatch, journal, browser, journal.controls)
    view = after.project()
    assert len(view.turns) == view.interactions == model.calls == browser.calls == 1
    assert (
        view.turns[0].generation.before_observation_ref
        == data.plan.initial_observation_ref
    )
    assert (
        view.current_observation(data.plan)
        == observed.interaction.result.observation_ref
    )


@pytest.mark.parametrize(
    "change",
    [
        "bool_revision",
        "negative_revision",
        "same_operation",
        "wrong_owner",
        "no_attempt",
        "execute_result",
        "wrong_parent",
        "allocation",
        "recovery",
        "cleanup_intent",
        "old_version",
        "extra",
    ],
)
def test_invalid_dispatch_never_records_or_sends(tmp_path: Path, change: str) -> None:
    _, journal, request, model = prepared(tmp_path)
    values = request.model_dump()
    command_op = values["intent"]["operation"]
    execute = values["intent"]["intent"]["operation"]
    result = values["result_operation"]
    if change == "bool_revision":
        values["expected_revision"] = True
    if change == "negative_revision":
        values["expected_revision"] = -1
    if change == "same_operation":
        result["operation_id"] = command_op["operation_id"]
    if change == "wrong_owner":
        result["owner_id"] = "other"
    if change == "no_attempt":
        execute["attempt_id"] = None
    if change == "execute_result":
        result["mode"] = "execute"
    if change == "wrong_parent":
        result["parent_operation_id"] = "other"
    if change == "allocation":
        result["allocation_id"] = "other"
    if change == "recovery":
        result["recovery_ref"] = request.intent.intent.input_ref.model_dump()
    if change == "cleanup_intent":
        command_op.update(mode="cleanup", parent_operation_id="parent")
    if change == "old_version":
        values["schema_version"] = "actor-dispatch/0"
    if change == "extra":
        values["surprise"] = True
    with pytest.raises((ValidationError, OwnershipConflict)):
        execute_actor_generation(
            cast(ActorDispatch, values), journal, model, journal.controls
        )
    assert (
        model.calls == 0
        and journal.read(command("read", attempt="attempt")).revision == 0
    )


@pytest.mark.parametrize("value", [None, "", 1, (), []])
def test_wrong_input_type_rejected_before_model(tmp_path: Path, value: object) -> None:
    _, journal, _, model = prepared(tmp_path)
    with pytest.raises(ValidationError):
        execute_actor_generation(
            cast(ActorDispatch, value), journal, model, journal.controls
        )
    assert model.calls == 0


def test_preflight_denied_does_not_leave_pending_intent(tmp_path: Path) -> None:
    _, journal, request, model = prepared(tmp_path)
    model.preflight_error = PermissionError(
        "unsupported public projection or revoked model authority"
    )
    with pytest.raises(ActorDispatchFailure) as caught:
        execute_actor_generation(request, journal, model, journal.controls)
    assert (
        caught.value.primary is model.preflight_error
        and caught.value.phase == "preflight"
    )
    assert (
        model.calls == 0
        and journal.read(command("read", attempt="attempt")).revision == 0
    )


@pytest.mark.parametrize("lost", [False, True])
def test_intent_failure_or_lost_ack_has_no_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lost: bool
) -> None:
    _, journal, request, model = prepared(tmp_path)
    append = journal.append

    def fail(
        event: TraceProgressEvent, revision: int, op: OperationContext
    ) -> TraceSnapshot:
        if lost:
            append(event, revision, op)
        raise OSError("intent failure")

    monkeypatch.setattr(journal, "append", fail)
    with pytest.raises(ActorDispatchFailure) as caught:
        execute_actor_generation(request, journal, model, journal.controls)
    assert caught.value.phase == "commit_intent" and model.calls == 0
    assert journal.read(command("read", attempt="attempt")).revision == int(lost)


@pytest.mark.parametrize(
    "error", [OSError("lost response"), TimeoutError("deadline"), KeyboardInterrupt()]
)
def test_model_exception_keeps_pending_original_and_never_infers_failed(
    tmp_path: Path, error: BaseException
) -> None:
    _, journal, request, model = prepared(tmp_path)
    model.failure = error
    with pytest.raises(ActorDispatchFailure) as caught:
        execute_actor_generation(request, journal, model, journal.controls)
    assert caught.value.primary is error and caught.value.__cause__ is error
    assert caught.value.phase == "generate" and caught.value.returned is None
    view = journal.read(command("read", attempt="attempt")).project()
    assert view.intent == request.intent.intent and not view.turns
    with pytest.raises(ActorDispatchFailure):
        execute_actor_generation(request, journal, model, journal.controls)
    assert model.calls == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation_id", "wrong"),
        ("request_id", "wrong"),
        ("status", "invalid"),
        ("before_observation_ref", None),
    ],
)
def test_wrong_return_retained_without_false_result(
    tmp_path: Path, field: str, value: object
) -> None:
    _, journal, request, model = prepared(tmp_path)
    model.result = model.result.model_copy(update={field: value})
    with pytest.raises(ActorDispatchFailure) as caught:
        execute_actor_generation(request, journal, model, journal.controls)
    assert (
        caught.value.phase == "validate_return"
        and caught.value.returned is model.result
    )
    assert caught.value.observed is None
    assert (
        model.calls == 1
        and journal.read(command("read", attempt="attempt")).revision == 1
    )


@pytest.mark.parametrize("after_commit", [False, True])
def test_result_commit_failure_keeps_exact_fact_for_cleanup_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, after_commit: bool
) -> None:
    _, journal, request, model = prepared(tmp_path)
    append = journal.append

    def fail(
        event: TraceProgressEvent, revision: int, op: OperationContext
    ) -> TraceSnapshot:
        if isinstance(event, GenerationObserved):
            if after_commit:
                append(event, revision, op)
            raise OSError("result confirmation lost")
        return append(event, revision, op)

    monkeypatch.setattr(journal, "append", fail)
    with pytest.raises(ActorDispatchFailure) as caught:
        execute_actor_generation(request, journal, model, journal.controls)
    failure = caught.value
    assert (
        failure.phase == "commit_result"
        and failure.observed is not None
        and failure.acknowledged is not None
    )
    cleanup = request.result_operation.cleanup(
        "reconcile", now=datetime.now(timezone.utc), seconds=30
    )
    after = append(failure.observed, failure.acknowledged.revision, cleanup)
    assert after.revision == 2 and model.calls == 1
    assert after.project().generation == model.result


@pytest.mark.parametrize("fail_on,revision", [(1, 0), (2, 0), (3, 1)])
def test_cancellation_before_send_never_calls_model(
    tmp_path: Path, fail_on: int, revision: int
) -> None:
    _, journal, request, model = prepared(tmp_path)
    with pytest.raises(ActorDispatchFailure):
        execute_actor_generation(
            request, journal, model, Controls(Checkpoints(fail_on))
        )
    assert (
        model.calls == 0
        and journal.read(command("read", attempt="attempt")).revision == revision
    )


def test_result_recording_survives_original_control_expiration(tmp_path: Path) -> None:
    _, journal, request, model = prepared(tmp_path)
    control = Checkpoints(4)
    after = execute_actor_generation(request, journal, model, Controls(control))
    assert after.revision == 2 and model.control is control and control.count == 3
    with pytest.raises(TimeoutError):
        control.checkpoint()


@pytest.mark.parametrize("denied", [True, False])
def test_live_journal_authority_and_revision_gate_before_send(
    tmp_path: Path, denied: bool
) -> None:
    data, journal, request, model = prepared(tmp_path)
    if denied:
        data.authority.denied = True
    else:
        request = request.model_copy(update={"expected_revision": 1})
    with pytest.raises(ActorDispatchFailure) as caught:
        execute_actor_generation(request, journal, model, journal.controls)
    assert caught.value.phase == "commit_intent" and model.calls == 0
