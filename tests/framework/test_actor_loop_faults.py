"""Loop stop/recording faults preserve original effects and never repeat a seal."""

from pathlib import Path
import pytest
from lab_generate_skill.application.actor_loop import ActorLoopFailure
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext, CancellationRef
from lab_generate_skill.domain.trace_events import (
    TraceProgressEvent,
    TraceSealed,
    GenerationPlanned,
    GenerationObserved,
)
from lab_generate_skill.domain.trace_events import GenerationIntent
from lab_generate_skill.domain.actor_generation import ActorGeneration
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from actor_loop_fixtures import case
from test_run_journal import command, CancelSwitch


@pytest.mark.parametrize("committed", [False, True])
def test_seal_intent_confirmation_loss_is_never_reappended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, committed: bool
) -> None:
    c = case(tmp_path, ('{"action":"send_msg_to_user(\'done\')"}',))
    append = c.journal.append
    seals = []

    def lost(
        event: TraceProgressEvent, revision: int, operation: OperationContext
    ) -> TraceSnapshot:
        if isinstance(event, TraceSealed):
            seals.append(event)
            if committed:
                append(event, revision, operation)
            raise OSError("seal confirmation unavailable")
        return append(event, revision, operation)

    monkeypatch.setattr(c.journal, "append", lost)
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    assert isinstance(caught.value.primary, OSError)
    assert len(seals) == c.model.calls == c.browser.calls == 1
    assert caught.value.snapshot is not None
    assert (caught.value.snapshot.project().sealed is not None) == committed


@pytest.mark.parametrize("committed", [False, True])
def test_unknown_stop_fact_put_keeps_candidate_without_second_put(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, committed: bool
) -> None:
    c = case(tmp_path, ('{"action":"send_msg_to_user(\'done\')"}',))
    put = c.store.put
    stops = []

    def lost(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        if metadata.content_schema == "trace-stop/1":
            stops.append(raw)
            if committed:
                put(raw, metadata, control, exchange_id=exchange_id)
            raise OSError("stop fact confirmation unavailable")
        return put(raw, metadata, control, exchange_id=exchange_id)

    monkeypatch.setattr(c.store, "put", lost)
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    assert len(stops) == c.model.calls == c.browser.calls == 1
    assert (
        getattr(caught.value.primary, "actor_fact_candidate").content_schema
        == "trace-stop/1"
    )
    assert (
        caught.value.snapshot is not None
        and caught.value.snapshot.project().sealed is None
    )


def test_cancellation_after_model_return_records_generation_and_stops_before_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = case(tmp_path)
    switch = CancelSwitch()
    controls = c.journal.controls
    assert isinstance(controls, OperationGuards)
    # Explicit test control channel; no real resource stop or production authority.
    monkeypatch.setattr(controls, "_cancellation", switch)
    c.request = c.request.model_copy(
        update={
            "operation": c.request.operation.model_copy(
                update={
                    "cancellation_ref": CancellationRef(
                        channel_id="cancel", run_id="run", owner_id="owner"
                    )
                }
            )
        }
    )
    generate = c.model.generate

    def cancelled(
        intent: GenerationIntent, *, control: OperationControl
    ) -> ActorGeneration:
        returned = generate(intent, control=control)
        switch.cancelled = True
        return returned

    monkeypatch.setattr(c.model, "generate", cancelled)
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    assert c.model.calls == 1 and c.browser.calls == 0
    assert caught.value.snapshot is not None
    trace = caught.value.snapshot.project().sealed
    assert (
        trace is not None
        and trace.generations == 1
        and trace.stop_reason == "cancelled"
    )
    assert trace.turns[0].generation.status == "completed"


@pytest.mark.parametrize("event_kind", ["intent", "response"])
def test_generation_commit_ack_loss_never_creates_second_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, event_kind: str
) -> None:
    c = case(tmp_path)
    append = c.journal.append

    def lost(
        event: TraceProgressEvent, revision: int, operation: OperationContext
    ) -> TraceSnapshot:
        after = append(event, revision, operation)
        if (event_kind == "intent" and isinstance(event, GenerationPlanned)) or (
            event_kind == "response" and isinstance(event, GenerationObserved)
        ):
            raise OSError("generation event confirmation unavailable")
        return after

    monkeypatch.setattr(c.journal, "append", lost)
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    assert c.model.calls == int(event_kind == "response") and c.browser.calls == 0
    assert caught.value.snapshot is not None
    view = caught.value.snapshot.project()
    if event_kind == "intent":
        assert view.sealed is None and view.intent is not None
    else:
        assert view.sealed is not None and view.sealed.stop_reason == "error"


def test_failure_read_error_preserves_first_error_and_original_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = case(tmp_path)
    original_read = c.journal.read
    primary = OSError("model lost reply")
    c.model.failure = primary

    def read(operation: OperationContext) -> TraceSnapshot:
        if operation.mode == "cleanup":
            raise OSError("independent read unavailable")
        return original_read(operation)

    monkeypatch.setattr(c.journal, "read", read)
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    assert getattr(caught.value.primary, "primary") is primary
    assert len(caught.value.cleanup_errors) == 1
    assert c.model.calls == 1 and c.browser.calls == 0
