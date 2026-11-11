"""Retain real journal/RPC sessions; physical processes/authority explicit doubles."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import pytest
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.return_publication import (
    BrowserReturnPublication,
)
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    ResourceRecord,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from browser_resource_fixtures import resource_case, ResourceCase
from browser_worker_fixtures import action
from test_browser_resource import inspect
from test_resource_journal import context


@pytest.fixture
def c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ResourceCase:
    return resource_case(tmp_path, monkeypatch)


def owner(
    c: ResourceCase, publication: BrowserReturnPublication | None = None
) -> RetainedBrowserResource:
    return RetainedBrowserResource(
        c.spec,
        c.op,
        journal=c.journal,
        evidence=c.evidence,
        controls=c.controls,
        clock=c.clock,
        authority=c.authority,
        return_publication=publication,
    )


def close(
    c: ResourceCase, held: RetainedBrowserResource, name: str = "close"
) -> ResourceRecord:
    op = c.op.cleanup(
        "retained-test-" + name, now=datetime.now(timezone.utc), seconds=30
    )
    return held.close(op, c.controls.bind(op))


@pytest.mark.parametrize("independent_return", [False, True])
def test_initial_session_stays_acquired_until_explicit_finalization(
    c: ResourceCase,
    independent_return: bool,
) -> None:
    publication = (
        BrowserReturnPublication(c.spec.token, c.controls, c.clock, 30)
        if independent_return
        else None
    )
    held = owner(c, publication)
    browser = held.open(c.controls.bind(c.op))
    assert browser.return_publication is publication
    assert held.session is browser and inspect(c).state == "acquired"
    initial, returned = browser.observation_ref, browser.last_return_ref
    assert (
        initial is not None
        and returned is not None
        and browser.resource_started_ref is not None
    )
    assert c.channels[0].finishes == 0
    with pytest.raises(DispatchAlreadyCommitted):
        held.open(c.controls.bind(c.op))
    op = context(c.spec.token, "step")
    assert (
        browser.step(action(), op, control=c.controls.bind(op)).before_observation_ref
        == initial
    )
    record = close(c, held)
    assert record.state == "closed" and held.closed == record
    assert [e.state for e in record.events] == [
        "registered",
        "acquiring",
        "acquired",
        "closing",
        "closed",
    ]
    assert close(c, held, "readonly-repeat") == record
    assert len(c.channels) == c.channels[0].starts == c.channels[0].finishes == 1
    with pytest.raises(OwnershipConflict):
        _ = held.session
    with pytest.raises(DispatchAlreadyCommitted):
        held.open(c.controls.bind(c.op))


def test_context_consumer_preserves_body_failure_and_original_ending(
    c: ResourceCase,
) -> None:
    error = TimeoutError("controlled consumer failure; no replay")
    held = owner(c)
    with pytest.raises(TimeoutError) as failed:
        with held:
            raise error
    assert failed.value is error and inspect(c).state == "closed"
    ending = json.loads(c.evidence.read(inspect(c).events[-1].evidence[0]))
    assert ending["details"]["primary"] is not None
    assert held.phase == "closed" and c.channels[0].finishes == 1


def test_partial_initialization_failure_only_reads_already_closed_record(
    c: ResourceCase,
) -> None:
    c.authority.deny_started = True
    held = owner(c)
    with pytest.raises(PermissionError) as failed:
        held.open(c.controls.bind(c.op))
    assert held.open_error is failed.value
    assert inspect(c).state == "closed"
    assert close(c, held).state == "closed"
    assert c.authority.close_calls == c.channels[0].finishes == 1


def test_lost_begin_ack_never_reacquires_or_closes_unowned_worker(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = c.journal.begin_acquire

    def lost(
        token: AllocationToken, ref: EvidenceRef, revision: int, op: OperationContext
    ) -> ResourceRecord:
        original(token, ref, revision, op)
        raise OSError("controlled acquisition acknowledgement loss")

    monkeypatch.setattr(c.journal, "begin_acquire", lost)
    held = owner(c)
    with pytest.raises(OSError):
        held.open(c.controls.bind(c.op))
    with pytest.raises(OwnershipConflict):
        close(c, held)
    with pytest.raises(DispatchAlreadyCommitted):
        held.open(c.controls.bind(c.op))
    assert inspect(c).state == "acquiring"
    assert c.channels[0].starts == c.channels[0].aborts == c.authority.close_calls == 0


class Cancelled:
    def checkpoint(self) -> float:
        raise OperationStopped("CANCELLED", "retained-unit")

    def wait(self, seconds: float) -> None:
        self.checkpoint()


def test_cancelled_close_still_attempts_original_physical_cleanup(
    c: ResourceCase,
) -> None:
    held = owner(c)
    held.open(c.controls.bind(c.op))
    op = c.op.cleanup("cancelled-close", now=datetime.now(timezone.utc), seconds=30)
    with pytest.raises(OperationStopped):
        held.close(op, Cancelled())
    assert inspect(c).state == "closed" and c.channels[0].finishes == 1
    assert close(c, held, "independent-read").state == "closed"
    assert c.channels[0].finishes == c.authority.close_calls == 1


def test_cancel_after_initial_return_retains_session_for_finalization(
    c: ResourceCase,
) -> None:
    held = owner(c)

    class AfterReturn:
        calls = 0

        def checkpoint(self) -> float:
            self.calls += 1
            if self.calls == 2:
                raise OperationStopped("CANCELLED", "after-initial")
            return 1.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(OperationStopped):
        held.open(AfterReturn())
    assert held.session.observation_ref is not None and inspect(c).state == "acquired"
    assert close(c, held).state == "closed"


def test_unknown_closure_remains_quarantined_and_is_not_retried(
    c: ResourceCase,
) -> None:
    held = owner(c)
    held.open(c.controls.bind(c.op))
    c.authority.deny_close = True
    with pytest.raises(BaseExceptionGroup) as failed:
        close(c, held)
    assert held.close_error is failed.value and inspect(c).state == "quarantined"
    with pytest.raises(OwnershipConflict):
        close(c, held, "readonly")
    assert c.authority.close_calls == c.channels[0].finishes == 1


@pytest.mark.parametrize("fault", ["foreign-parent", "foreign-attempt", "thread"])
def test_wrong_cleanup_identity_does_not_touch_owned_browser(
    c: ResourceCase, fault: str
) -> None:
    held = owner(c)
    held.open(c.controls.bind(c.op))
    op = c.op.cleanup("bad-close", now=datetime.now(timezone.utc), seconds=30)
    if fault == "thread":
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(held.close, op, c.controls.bind(op))
            with pytest.raises(OwnershipConflict):
                future.result()
    else:
        op = op.model_copy(
            update={
                (
                    "parent_operation_id" if fault == "foreign-parent" else "attempt_id"
                ): "foreign"
            }
        )
        with pytest.raises(OwnershipConflict):
            held.close(op, c.controls.bind(op))
    assert inspect(c).state == "acquired" and c.channels[0].finishes == 0
    close(c, held, "original-valid")


@pytest.mark.parametrize("invalid", [None, "", {}, [], True, 1])
def test_invalid_spec_and_missing_authority_rejected_before_effect(
    c: ResourceCase, invalid: Any
) -> None:
    with pytest.raises((TypeError, ValueError)):
        RetainedBrowserResource(
            invalid,
            c.op,
            journal=c.journal,
            evidence=c.evidence,
            controls=c.controls,
            clock=c.clock,
            authority=c.authority,
        )
    absent: Any = None
    with pytest.raises(ValueError, match="mandatory"):
        RetainedBrowserResource(
            c.spec,
            c.op,
            journal=c.journal,
            evidence=c.evidence,
            controls=c.controls,
            clock=c.clock,
            authority=absent,
        )
    assert not c.channels


def test_maximum_original_operation_identity_is_preserved_in_close(
    c: ResourceCase,
) -> None:
    c.op = c.op.model_copy(update={"operation_id": "x" * 256})
    held = owner(c)
    with held:
        assert inspect(c).state == "acquired"
    assert held.closed is not None and held.closed.events[1].operation == c.op


@pytest.mark.parametrize("fault", ["token", "schema", "cleanup-error"])
def test_false_ending_does_not_pass_readonly_reconciliation(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    held = owner(c)
    held.open(c.controls.bind(c.op))
    record = close(c, held)
    ending_ref = record.events[-1].evidence[0]
    body = json.loads(c.evidence.read(ending_ref))
    if fault == "token":
        body["token"]["allocation_id"] = "foreign"
    elif fault == "schema":
        body["schema_version"] = "unrelated-fact/1"
    else:
        body["details"]["cleanup_errors"] = ["controlled unconfirmed cleanup"]
    op = c.op.cleanup(
        "false-ending-fixture", now=datetime.now(timezone.utc), seconds=30
    )
    bad_ref = c.evidence.put(
        json.dumps(body).encode(),
        EvidenceMetadata(
            media_type=ending_ref.media_type,
            content_schema=ending_ref.content_schema,
            visibility=ending_ref.visibility,
            producer=ending_ref.producer,
        ),
        control=c.controls.bind(op),
    )
    changed = record.model_copy(
        update={
            "events": (
                *record.events[:-1],
                record.events[-1].model_copy(update={"evidence": (bad_ref,)}),
            )
        }
    )
    with monkeypatch.context() as patch:
        patch.setattr(c.journal, "read", lambda *args, **kwargs: changed)
        with pytest.raises(OwnershipConflict):
            close(c, held, "false-ending")
    assert close(c, held, "original-ending") == record
    assert c.channels[0].finishes == c.authority.close_calls == 1


def test_exit_clock_failure_cannot_skip_original_physical_close(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = owner(c)
    held.open(c.controls.bind(c.op))

    def failed_clock() -> datetime:
        raise OSError("controlled cleanup clock failure")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(c.clock, "utcnow", failed_clock)
            with pytest.raises(BaseExceptionGroup):
                held.__exit__(None, None, None)
        assert c.channels[0].finishes == 1
        assert c.channels[0].capture.termination is not None
        assert held.phase == "close-unconfirmed"
    finally:
        # The broken implementation has not exited at all; clean this explicit
        # unit worker after recording the reproducer, never retry an unknown IO.
        if held.phase == "open":
            close(c, held, "unit-reproducer-finally")


@pytest.mark.parametrize("body_failure", [False, True])
def test_exit_control_failure_keeps_body_error_and_still_closes(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch, body_failure: bool
) -> None:
    held = owner(c)
    original = c.controls.bind
    prelude = OSError("controlled cleanup control binding failure")
    primary = TimeoutError("original consumer failure")

    def failed(operation: OperationContext) -> OperationControl:
        if operation.operation_id.startswith("browser-retained-close-read-"):
            raise prelude
        return original(operation)

    expected: type[BaseException] = BaseExceptionGroup if body_failure else OSError
    with monkeypatch.context() as patch:
        patch.setattr(c.controls, "bind", failed)
        with pytest.raises(expected) as caught:
            with held:
                if body_failure:
                    raise primary
        assert held.phase == "close-unconfirmed" and held.closed is None
        assert held.close_error is caught.value

    def leaves(error: BaseException) -> list[BaseException]:
        if isinstance(error, BaseExceptionGroup):
            return [leaf for child in error.exceptions for leaf in leaves(child)]
        return [error]

    errors = leaves(caught.value)
    assert prelude in errors and (primary in errors) == body_failure
    assert inspect(c).state == "closed" and c.channels[0].finishes == 1
    assert close(c, held, "independent-after-bind-failure").state == "closed"
    assert c.channels[0].finishes == c.authority.close_calls == 1
