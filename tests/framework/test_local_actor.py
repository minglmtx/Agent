"""Original trace-to-worker recording and persistent refusal after unknown sends."""

from datetime import datetime, timezone
from pathlib import Path
from dataclasses import replace
from typing import Any
import pytest
from lab_generate_skill.application.actor_generation import (
    execute_actor_generation,
    ActorDispatchFailure,
)
from lab_generate_skill.application.actor_loop import RecordedActorRunner
from lab_generate_skill.adapters.models.local_actor import LocalActorUnconfirmed
from lab_generate_skill.domain.actor_dispatch import ActorDispatch
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.actor_engine import LocalActorOutput
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.trace_events import GenerationPlanned
from lab_generate_skill.ports.lifecycle import OperationControl
from local_actor_fixtures import case, Case
from retrieval_fixtures import reference


def dispatch(c: Case) -> ActorDispatch:
    return ActorDispatch(
        intent=GenerationPlanned(operation=c.event_op, intent=c.intent),
        expected_revision=0,
        result_operation=c.intent.operation.cleanup(
            "local-record-result", now=datetime.now(timezone.utc), seconds=15
        ),
    )


def test_original_trace_records_one_actual_exchange_and_response(
    tmp_path: Path,
) -> None:
    c = case(tmp_path)
    result = execute_actor_generation(
        dispatch(c), c.loop.journal, c.model, c.loop.journal.controls
    )
    actual = result.project().generation
    assert actual is not None and actual.response_ref is not None
    assert c.intent.matches(actual) and c.loader.session.calls == 1
    response = ActorTextCompletion.model_validate_json(
        c.loop.store.read(actual.response_ref)
    )
    assert (
        response.text == c.loader.session.output.text
        and response.request_id == c.intent.request_id
    )
    assert len(c.authority.completed) == 1
    assert len(list(c.root.glob("*.local-actor-call.json"))) == 1
    with pytest.raises(ActorDispatchFailure):
        execute_actor_generation(
            dispatch(c), c.loop.journal, c.new_model(), c.loop.journal.controls
        )
    assert c.loader.session.calls == 1


def test_missing_trace_intent_and_denied_permission_do_not_consume(
    tmp_path: Path,
) -> None:
    c = case(tmp_path)
    control = c.loop.journal.controls.bind(c.intent.operation)
    with pytest.raises(OwnershipConflict):
        c.model.generate(c.intent, control=control)
    c.authority.denied = True
    with pytest.raises(PermissionError):
        c.model.validate(c.intent, control=control)
    assert not list(c.root.iterdir()) and c.loader.session.calls == 0


def test_unknown_worker_outcome_keeps_original_marker_and_never_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = case(tmp_path)
    original = c.channel.exchange
    unknown = OSError("actual return lost")

    def exchange(raw: bytes, control: OperationControl) -> bytes:
        from lab_generate_skill.adapters.models.actor_worker_protocol import (
            decode_command,
        )

        reply = original(raw, control)
        if decode_command(raw).operation == "generate":
            raise unknown
        return reply

    monkeypatch.setattr(c.channel, "exchange", exchange)
    with pytest.raises(ActorDispatchFailure) as caught:
        execute_actor_generation(
            dispatch(c), c.loop.journal, c.model, c.loop.journal.controls
        )
    failure = caught.value.primary
    assert isinstance(failure, LocalActorUnconfirmed) and failure.primary is unknown
    assert (
        c.loader.session.calls == 1
        and c.loop.journal.read(c.authority.read_op).project().intent == c.intent
    )
    with pytest.raises(LocalActorUnconfirmed) as repeated:
        c.new_model().generate(
            c.intent, control=c.loop.journal.controls.bind(c.intent.operation)
        )
    assert (
        isinstance(repeated.value.primary, DispatchAlreadyCommitted)
        and c.loader.session.calls == 1
    )


@pytest.mark.parametrize(
    "schema",
    [
        "actor-worker-command/1",
        "actor-worker-reply/1",
        "actor-model-response/1",
        "local-actor-execution/1",
    ],
)
def test_publication_ack_loss_retains_exchange_candidates_and_does_not_repeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schema: str
) -> None:
    c = case(tmp_path)
    original = c.loop.store.put
    lost = OSError("commit acknowledgement lost")

    def put(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        actual = original(raw, metadata, control, exchange_id=exchange_id)
        if metadata.content_schema == schema:
            raise lost
        return actual

    monkeypatch.setattr(c.loop.store, "put", put)
    with pytest.raises(ActorDispatchFailure) as caught:
        execute_actor_generation(
            dispatch(c), c.loop.journal, c.model, c.loop.journal.controls
        )
    failure = caught.value.primary
    assert isinstance(failure, LocalActorUnconfirmed) and failure.primary is lost
    assert (
        failure.exchange is not None and failure.retained[-1].content_schema == schema
    )
    assert c.loop.store.read(failure.retained[-1])
    with pytest.raises(LocalActorUnconfirmed) as repeated:
        c.new_model().generate(
            c.intent, control=c.loop.journal.controls.bind(c.intent.operation)
        )
    assert isinstance(repeated.value.primary, DispatchAlreadyCommitted)
    assert c.loader.session.calls == 1


def test_recorded_local_model_connects_actual_trace_decisions_and_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = case(tmp_path)
    original = c.loader.session.infer

    def infer(*args: Any) -> LocalActorOutput:
        if c.loader.session.calls == 1:
            c.loader.session.output = c.loader.session.output.model_copy(
                update={"text": '{"action":"send_msg_to_user(\'Saved\')"}'}
            )
        return original(*args)

    monkeypatch.setattr(c.loader.session, "infer", infer)
    params = c.intent.parameters_ref
    request = c.loop.request.model_copy(
        update={
            "model_allocation": c.binding.resource,
            "parameters_refs": (params,) * len(c.loop.request.parameters_refs),
        }
    )
    deps = replace(c.loop.runner.deps, model=c.model)
    result = RecordedActorRunner(deps).run(request)
    trace = result.project().sealed
    assert trace is not None and trace.stop_reason == "finished"
    assert c.loader.session.calls == 2 and c.loop.browser.calls == 2
    assert (
        len(c.authority.completed) == 2
        and len(list(c.root.glob("*.local-actor-call.json"))) == 2
    )
