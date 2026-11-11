"""Actual parse/journal/stop consumers share bounded bodies, never permissions."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest

import lab_generate_skill.application.actor_loop as loop
from lab_generate_skill.actor.decisions import RecordedActorDecisions
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.ports.actor_context import ActorDecisionInputReads
from lab_generate_skill.application.actor_rejection_progress import (
    ActorInvalidProposalsStopped,
    check_repeated_invalid_proposals,
)
from lab_generate_skill.domain.actor_engine import LocalActorOutput
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.trace_events import (
    DecisionRejected,
    ReadPlanned,
    ActionPlanned,
)
from adaptive_actor_loop_fixtures import adaptive_loop_case


def case(root: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    c = adaptive_loop_case(
        root,
        read_policy_changes={
            "schema_version": "observation-read-policy/2",
            "max_consecutive_invalid_proposals": 3,
            "max_identical_invalid_proposals": 2,
            "warn_remaining": 3,
        },
    )
    d = c.runner.deps
    assert isinstance(d.journal, FileTraceJournal)
    assert isinstance(d.journal.generation_inputs, ActorDecisionInputReads)
    decisions = RecordedActorDecisions(
        d.evidence, d.controls, proposals=c.sources, inputs=d.journal.generation_inputs
    )
    c.runner = loop.RecordedActorRunner(replace(d, decisions=decisions))

    def infer(tokens: Any, parameters: Any, control: Any) -> LocalActorOutput:
        assert c.session.last_prompt is not None
        c.session.prompts.append(c.session.last_prompt)
        c.session.calls += 1
        return LocalActorOutput(
            text='{"thought":"Inspect the public page","action":"goto(http://unit.invalid/)"}',
            finish_reason="stop",
            prompt_tokens=len(tokens),
            completion_tokens=2,
        )

    monkeypatch.setattr(c.session, "infer", infer)
    return c


@pytest.mark.parametrize("deadline_on_extra_read", [False, True])
def test_parse_publication_journal_and_stop_reuse_exact_bodies_before_next_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deadline_on_extra_read: bool
) -> None:
    c = case(tmp_path, monkeypatch)
    d = c.runner.deps
    decisions = d.decisions
    phase = "outside"
    physical: Counter[str] = Counter()
    readers = []
    original_read, original_decide = d.evidence.read, decisions.decide
    original_append, original_stop = (
        d.journal.append,
        check_repeated_invalid_proposals,
    )

    def read(ref: Any, control: Any = None) -> bytes:
        if phase != "outside":
            physical[phase] += 1
        if deadline_on_extra_read and phase in ("journal", "stop"):
            raise OperationStopped("DEADLINE_EXCEEDED", "unnecessary-original-read")
        raw = original_read(ref, control=control)
        assert isinstance(raw, bytes)
        return raw

    def decide(generation: Any, task: Any, operation: Any) -> Any:
        nonlocal phase
        phase = "parse"
        try:
            result = original_decide(generation, task, operation)
            readers.append(
                decisions.rejected_inputs(
                    generation, result, d.controls.bind(operation)
                )
            )
            return result
        finally:
            phase = "outside"

    def append(event: Any, *args: Any) -> Any:
        nonlocal phase
        phase = "journal" if isinstance(event, DecisionRejected) else "outside"
        try:
            return original_append(event, *args)
        finally:
            phase = "outside"

    def stop(snapshot: Any, reader: Any, control: Any) -> None:
        nonlocal phase
        assert reader is readers[-1]
        phase = "stop"
        try:
            return original_stop(snapshot, reader, control)
        finally:
            phase = "outside"

    monkeypatch.setattr(d.evidence, "read", read)
    monkeypatch.setattr(decisions, "decide", decide)
    monkeypatch.setattr(d.journal, "append", append)
    monkeypatch.setattr(loop, "check_repeated_invalid_proposals", stop)
    with pytest.raises(loop.ActorLoopFailure) as caught:
        c.runner.run(c.request)
    failure = caught.value
    assert isinstance(failure.primary, ActorInvalidProposalsStopped)
    assert failure.primary.count == failure.primary.limit == c.session.calls == 2
    assert physical == {"parse": 2}  # Mandatory original readback of each new failure.
    assert len(readers) == 2 and readers[0] is not readers[1]
    assert failure.snapshot is not None and failure.cleanup_errors == ()
    assert sum(isinstance(e, DecisionRejected) for e in failure.snapshot.events) == 2
    assert not any(
        isinstance(e, (ReadPlanned, ActionPlanned)) for e in failure.snapshot.events
    )
    assert all(
        p.observation_view.reads_used == p.observation_view.no_progress == 0
        for p in c.session.prompts
    )
    control = d.controls.bind(failure.snapshot.events[-1].operation)
    for reader in readers:
        with pytest.raises(OwnershipConflict):
            reader.read(c.request.initial_observation_ref, control)


@pytest.mark.parametrize("fault", ["request", "generation", "closed", "thread"])
def test_decision_supplier_refuses_foreign_or_expired_generation_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = case(tmp_path, monkeypatch)
    d = c.runner.deps
    decisions = d.decisions
    original = decisions.decide

    def decide(generation: Any, task: Any, operation: Any) -> Any:
        control = d.controls.bind(operation)
        provider = decisions.inputs
        if fault in ("request", "generation"):
            field = "request_id" if fault == "request" else "generation_id"
            foreign = generation.model_copy(update={field: "foreign"})
            with pytest.raises(OwnershipConflict):
                provider.decision_inputs(foreign, control)
        elif fault == "thread":
            with ThreadPoolExecutor(max_workers=1) as executor:
                with pytest.raises(OwnershipConflict):
                    executor.submit(
                        provider.decision_inputs, generation, control
                    ).result()
        else:
            provider.clear_inputs()
            with pytest.raises(OwnershipConflict):
                provider.decision_inputs(generation, control)
            raise OwnershipConflict("Expired decision input lifetime")
        result = original(generation, task, operation)
        with pytest.raises(OwnershipConflict):
            decisions.rejected_inputs(
                generation,
                result.model_copy(update={"generation_id": "foreign"}),
                control,
            )
        return result

    monkeypatch.setattr(decisions, "decide", decide)
    with pytest.raises(loop.ActorLoopFailure) as caught:
        c.runner.run(c.request)
    assert isinstance(
        caught.value.primary,
        OwnershipConflict if fault == "closed" else ActorInvalidProposalsStopped,
    )
    assert c.session.calls == (1 if fault == "closed" else 2)


@pytest.mark.parametrize("fault", ["before_put", "after_put", "readback", "corrupt"])
def test_uncertain_rejection_publication_has_no_confirmed_body_or_stop_fact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = case(tmp_path, monkeypatch)
    d = c.runner.deps
    put0, read0 = d.evidence.put, d.evidence.read

    def put(data: Any, metadata: Any, control: Any = None) -> Any:
        if metadata.content_schema == "actor-parse-failure/1" and fault == "before_put":
            raise OSError("Original publication refused")
        ref = put0(data, metadata, control=control)
        if metadata.content_schema == "actor-parse-failure/1" and fault == "after_put":
            raise OSError("Original publication acknowledgement lost")
        return ref

    def read(ref: Any, control: Any = None) -> bytes:
        if ref.content_schema == "actor-parse-failure/1":
            if fault == "readback":
                raise OSError("Original publication readback unavailable")
            if fault == "corrupt":
                return b"corrupt persisted body"
        raw = read0(ref, control=control)
        assert isinstance(raw, bytes)
        return raw

    monkeypatch.setattr(d.evidence, "put", put)
    monkeypatch.setattr(d.evidence, "read", read)
    with pytest.raises(loop.ActorLoopFailure) as caught:
        c.runner.run(c.request)
    failure = caught.value
    assert isinstance(
        failure.primary, EvidenceIntegrityError if fault == "corrupt" else OSError
    )
    assert c.session.calls == 1 and failure.snapshot is not None
    assert not any(isinstance(e, DecisionRejected) for e in failure.snapshot.events)
    sealed = failure.snapshot.project().sealed
    assert sealed is not None
    generation = sealed.turns[0].generation
    with pytest.raises(OwnershipConflict):
        d.decisions.rejected_inputs(
            generation, None, d.controls.bind(generation.operation)
        )


def test_rejection_publication_keeps_current_journal_permission_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = case(tmp_path, monkeypatch)
    d = c.runner.deps
    authority = d.journal.verifier.authority
    original = authority.verify_event
    refused = []

    def verify(snapshot: Any, event: Any, operation: Any) -> None:
        if isinstance(event, DecisionRejected):
            refused.append(event)
            raise OwnershipConflict("Current trace authority revoked")
        original(snapshot, event, operation)

    monkeypatch.setattr(authority, "verify_event", verify)
    with pytest.raises(loop.ActorLoopFailure) as caught:
        c.runner.run(c.request)
    assert isinstance(caught.value.primary, OwnershipConflict)
    assert len(refused) == c.session.calls == 1
    assert caught.value.snapshot is not None
    assert not any(
        isinstance(e, DecisionRejected) for e in caught.value.snapshot.events
    )
