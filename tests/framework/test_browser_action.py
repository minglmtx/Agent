"""Real trace transactions with an explicit engineering browser capability.

This checks application ordering and failure reconciliation, not website/model
permission or actual browser capture. No real website actions are issued.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.browser_action import (
    execute_browser_action,
    BrowserDispatchFailure,
)
from lab_generate_skill.domain.browser import BrowserAction, StepResult
from lab_generate_skill.domain.browser_dispatch import BrowserDispatch
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.trace_events import (
    ActionPlanned,
    InteractionObserved,
    TraceProgressEvent,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from trace_journal_fixtures import fixture, LiveTraceFixture
from test_run_journal import command


class Browser:
    def __init__(
        self, journal: FileTraceJournal, request: BrowserDispatch, result: StepResult
    ) -> None:
        self.journal, self.request, self.result = journal, request, result
        self.calls = 0
        self.failure: BaseException | None = None
        self.control: OperationControl | None = None

    def step(
        self,
        action: BrowserAction,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> StepResult:
        # The original intent must be on disk before even entering the backend.
        snapshot = self.journal.read(command("inspect-intent", attempt="attempt"))
        assert snapshot.events[-1] == self.request.intent
        assert operation == self.request.intent.execution_operation
        assert action == self.request.intent.decision.action
        self.calls += 1
        self.control = control
        if self.failure is not None:
            raise self.failure
        return self.result


def prepared(
    root: Path,
) -> tuple[LiveTraceFixture, FileTraceJournal, BrowserDispatch, Browser]:
    data = fixture(root, outcomes=("returned",))
    journal = data.journal()
    journal.create(data.plan, command("create", attempt="attempt"))
    events = data.events()
    for index, event in enumerate(events[:2]):
        journal.append(event, index, event.operation)
    intent = events[2]
    assert isinstance(intent, ActionPlanned)
    result_op = intent.execution_operation.cleanup(
        "record-result", now=datetime.now(timezone.utc), seconds=60
    )
    request = BrowserDispatch(
        intent=intent, expected_revision=2, result_operation=result_op
    )
    fact = events[3]
    assert isinstance(fact, InteractionObserved) and fact.interaction.result is not None
    return data, journal, request, Browser(journal, request, fact.interaction.result)


def test_commit_then_execute_then_record_and_repeat_never_redispatches(
    tmp_path: Path,
) -> None:
    _, journal, request, browser = prepared(tmp_path)
    after = execute_browser_action(request, journal, browser, journal.controls)
    assert (
        after.revision == 4 and after.project().interactions == 1 and browser.calls == 1
    )
    assert after.project().turns[0].interaction is not None
    assert journal.read(command("read-after", attempt="attempt")) == after
    with pytest.raises(BrowserDispatchFailure) as caught:
        execute_browser_action(request, journal, browser, journal.controls)
    assert isinstance(caught.value.primary, DispatchAlreadyCommitted)
    assert caught.value.phase == "commit_intent" and browser.calls == 1


@pytest.mark.parametrize(
    "change",
    [
        "revision_bool",
        "negative_revision",
        "same_operation",
        "wrong_owner",
        "no_attempt",
        "execute_result",
        "wrong_parent",
        "allocation",
        "cleanup_intent",
        "missing_action",
        "extra",
        "old_version",
    ],
)
def test_bad_request_has_no_new_intent_or_browser_effect(
    tmp_path: Path, change: str
) -> None:
    _, journal, request, browser = prepared(tmp_path)
    values = request.model_dump()
    intent = values["intent"]
    if change == "revision_bool":
        values["expected_revision"] = True
    if change == "negative_revision":
        values["expected_revision"] = -1
    if change == "same_operation":
        values["result_operation"]["operation_id"] = intent["operation"]["operation_id"]
    if change == "wrong_owner":
        values["result_operation"]["owner_id"] = "other"
    if change == "no_attempt":
        intent["execution_operation"]["attempt_id"] = None
    if change == "execute_result":
        values["result_operation"]["mode"] = "execute"
    if change == "wrong_parent":
        values["result_operation"]["parent_operation_id"] = "other"
    if change == "allocation":
        values["result_operation"]["allocation_id"] = "other"
    if change == "cleanup_intent":
        intent["operation"].update(mode="cleanup", parent_operation_id="parent")
    if change == "missing_action":
        intent["decision"]["action"] = None
    if change == "extra":
        values["surprise"] = True
    if change == "old_version":
        values["schema_version"] = "browser-dispatch/0"
    with pytest.raises((ValidationError, OwnershipConflict)):
        execute_browser_action(
            cast(BrowserDispatch, values), journal, browser, journal.controls
        )
    assert journal.read(command("read", attempt="attempt")).revision == 2
    assert browser.calls == 0


@pytest.mark.parametrize("value", [None, "", 1, (), []])
def test_wrong_input_types_rejected_without_dispatch(
    tmp_path: Path, value: object
) -> None:
    _, journal, _, browser = prepared(tmp_path)
    with pytest.raises(ValidationError):
        execute_browser_action(
            cast(BrowserDispatch, value), journal, browser, journal.controls
        )
    assert browser.calls == 0


@pytest.mark.parametrize("lost", [False, True])
def test_intent_commit_failure_never_calls_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lost: bool
) -> None:
    _, journal, request, browser = prepared(tmp_path)
    append = journal.append

    def fail(
        event: TraceProgressEvent, revision: int, op: OperationContext
    ) -> TraceSnapshot:
        if lost:
            append(event, revision, op)
        raise OSError("intent commit or cleanup failure")

    monkeypatch.setattr(journal, "append", fail)
    with pytest.raises(BrowserDispatchFailure) as caught:
        execute_browser_action(request, journal, browser, journal.controls)
    assert browser.calls == 0 and caught.value.phase == "commit_intent"
    assert caught.value.__cause__ is caught.value.primary
    assert journal.read(command("read", attempt="attempt")).revision == (
        3 if lost else 2
    )


@pytest.mark.parametrize(
    "error",
    [OSError("lost browser return"), TimeoutError("deadline"), KeyboardInterrupt()],
)
def test_backend_failure_preserves_pending_action_without_retry(
    tmp_path: Path, error: BaseException
) -> None:
    _, journal, request, browser = prepared(tmp_path)
    browser.failure = error
    with pytest.raises(BrowserDispatchFailure) as caught:
        execute_browser_action(request, journal, browser, journal.controls)
    assert caught.value.primary is error and caught.value.phase == "step"
    assert caught.value.returned is None and caught.value.observed is None
    assert (
        browser.calls == 1
        and journal.read(command("read", attempt="attempt")).project().action
        == request.intent
    )
    with pytest.raises(BrowserDispatchFailure):
        execute_browser_action(request, journal, browser, journal.controls)
    assert browser.calls == 1


@pytest.mark.parametrize(
    "field,value",
    [("action_id", "wrong"), ("before_observation_ref", None), ("terminal", "false")],
)
def test_invalid_return_kept_for_diagnosis_and_not_recorded(
    tmp_path: Path, field: str, value: object
) -> None:
    _, journal, request, browser = prepared(tmp_path)
    browser.result = browser.result.model_copy(update={field: value})
    with pytest.raises(BrowserDispatchFailure) as caught:
        execute_browser_action(request, journal, browser, journal.controls)
    assert (
        caught.value.phase == "validate_return"
        and caught.value.returned is browser.result
    )
    assert (
        browser.calls == 1
        and journal.read(command("read", attempt="attempt")).revision == 3
    )


@pytest.mark.parametrize("after_commit", [False, True])
def test_result_failure_keeps_exact_fact_for_cleanup_without_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, after_commit: bool
) -> None:
    _, journal, request, browser = prepared(tmp_path)
    append = journal.append

    def fail(
        event: TraceProgressEvent, revision: int, op: OperationContext
    ) -> TraceSnapshot:
        if isinstance(event, InteractionObserved):
            if after_commit:
                append(event, revision, op)
            raise OSError("result confirmation lost")
        return append(event, revision, op)

    monkeypatch.setattr(journal, "append", fail)
    with pytest.raises(BrowserDispatchFailure) as caught:
        execute_browser_action(request, journal, browser, journal.controls)
    failure = caught.value
    assert (
        failure.phase == "commit_result"
        and failure.observed is not None
        and failure.acknowledged is not None
    )
    cleanup = request.result_operation.cleanup(
        "reconcile-result", now=datetime.now(timezone.utc), seconds=30
    )
    after = append(failure.observed, failure.acknowledged.revision, cleanup)
    assert (
        after.revision == 4 and after.project().interactions == 1 and browser.calls == 1
    )


class Checkpoints:
    def __init__(self, fail_on: int) -> None:
        self.count, self.fail_on = 0, fail_on

    def checkpoint(self) -> float:
        self.count += 1
        if self.count >= self.fail_on:
            raise TimeoutError("original control stopped")
        return 60.0

    def wait(self, seconds: float) -> None:
        self.checkpoint()


class Controls:
    def __init__(self, control: Checkpoints) -> None:
        self.control = control

    def bind(self, operation: OperationContext) -> OperationControl:
        return self.control


@pytest.mark.parametrize("fail_on,revision", [(1, 2), (2, 3)])
def test_original_control_before_and_after_intent_prevents_action(
    tmp_path: Path, fail_on: int, revision: int
) -> None:
    _, journal, request, browser = prepared(tmp_path)
    controls: OperationControls = Controls(Checkpoints(fail_on))
    with pytest.raises(BrowserDispatchFailure):
        execute_browser_action(request, journal, browser, controls)
    assert (
        browser.calls == 0
        and journal.read(command("read", attempt="attempt")).revision == revision
    )


def test_successful_return_is_recorded_even_when_original_control_stops(
    tmp_path: Path,
) -> None:
    _, journal, request, browser = prepared(tmp_path)
    control = Checkpoints(3)
    after = execute_browser_action(request, journal, browser, Controls(control))
    assert browser.control is control
    assert after.revision == 4 and control.count == 2
    with pytest.raises(TimeoutError):
        control.checkpoint()


@pytest.mark.parametrize("denied", [True, False])
def test_live_authority_or_stale_revision_rejects_before_browser(
    tmp_path: Path, denied: bool
) -> None:
    data, journal, request, browser = prepared(tmp_path)
    if denied:
        data.authority.denied = True
    else:
        request = request.model_copy(update={"expected_revision": 1})
    with pytest.raises(BrowserDispatchFailure) as caught:
        execute_browser_action(request, journal, browser, journal.controls)
    assert caught.value.phase == "commit_intent" and browser.calls == 0
    assert journal.read(command("read", attempt="attempt")).revision == 2
