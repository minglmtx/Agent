"""Actual complete reviewer checks readonly and business turns without replay."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.plans.actor_closed_review import (
    review_actor,
    read_fact,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_events import GenerationIntent
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.context_preparation import ContextPreparationReceipt
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.evidence import EvidenceRef
from adaptive_actor_review_fixtures import closed_adaptive_review


def test_actual_closed_actor_review_checks_both_model_calls_native_read_and_one_business_return(
    tmp_path: Path,
) -> None:
    c = closed_adaptive_review(tmp_path)
    a = c.actor
    controls = a.base.base.loop.journal.controls
    sent = len(a.base.base.channel.sent)
    summary = review_actor(
        a.request,
        c.snapshot,
        tuple(a.executions),
        a.base.base.loop.store,
        controls,
        c.operation,
        context=c.context,
    )
    assert summary == dict(generations=2, interactions=1, stop_reason="finished")
    assert (
        len(a.base.base.channel.sent) == sent
        and a.session.calls == 2
        and a.session.closed == 1
    )
    c.context.clear_inputs()


def test_actual_review_refuses_an_input_only_verifier_when_the_trace_contains_reading(
    tmp_path: Path,
) -> None:
    c = closed_adaptive_review(tmp_path)
    a = c.actor

    class InputsOnly:
        def verify(
            self,
            request: ActorRunRequest,
            before: TraceSnapshot,
            intent: GenerationIntent,
            operation: OperationContext,
            *,
            control: OperationControl,
        ) -> ActorPrompt:
            return c.context.verify(request, before, intent, operation, control=control)

    with pytest.raises(EvidenceIntegrityError, match="read-event verifier is missing"):
        review_actor(
            a.request,
            c.snapshot,
            tuple(a.executions),
            a.base.base.loop.store,
            a.base.base.loop.journal.controls,
            c.operation,
            context=InputsOnly(),
        )


@pytest.mark.parametrize("fault", ["native_count", "public_bytes", "proposal"])
def test_original_read_proof_refuses_changed_native_count_result_or_model_proposal(
    tmp_path: Path, fault: str
) -> None:
    c = closed_adaptive_review(tmp_path)
    a = c.actor
    store = a.base.base.loop.store
    control = a.base.base.loop.journal.controls.bind(c.operation)
    trace = c.snapshot.project().sealed
    assert trace is not None
    turn = trace.turns[0]
    fact = turn.reading
    assert (
        fact is not None
        and fact.result is not None
        and turn.generation.response_ref is not None
    )
    prompt = read_fact(store, turn.generation.input_ref, ActorPrompt, control)
    completion = read_fact(
        store, turn.generation.response_ref, ActorTextCompletion, control
    )
    if fault == "native_count":
        assert turn.generation.context_preparation_ref is not None
        receipt = read_fact(
            store,
            turn.generation.context_preparation_ref,
            ContextPreparationReceipt,
            control,
        )
        wrong = fact.result.count.model_copy(
            update={"evidence_ref": receipt.counts[0].evidence_ref}
        )
        record = fact.result.model_copy(update={"count": wrong})
        turn = turn.model_copy(
            update={"reading": fact.model_copy(update={"result": record})}
        )
    elif fault == "public_bytes":
        original = c.context.evidence
        result_ref = fact.result.result_ref

        class BadBytes:
            def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
                raw = original.read(reference, control)
                return raw + b" " if reference == result_ref else raw

        c.context.evidence = BadBytes()
    else:
        data = json.loads(completion.text)
        data["read"]["output_tokens"] = fact.request.output_tokens - 1
        completion = completion.model_copy(update={"text": json.dumps(data)})
    sent = len(a.base.base.channel.sent)
    with pytest.raises(EvidenceIntegrityError):
        c.context.verify_reading(
            a.request, turn, prompt, completion, c.operation, control=control
        )
    assert len(a.base.base.channel.sent) == sent and a.session.calls == 2
