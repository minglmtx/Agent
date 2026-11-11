"""Dispatch boundaries: immutable route, original tombstone and cleanup context."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.models.actor_call_gate import consume_call
from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
from lab_generate_skill.adapters.models.actor_worker_exchange import ActorWorkerExchange
from lab_generate_skill.domain.local_actor import LocalActorCall, LocalActorBinding
from lab_generate_skill.domain.actor_prompt import MAX_ACTOR_INPUT_BYTES
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.application.actor_generation import (
    execute_actor_generation,
    ActorDispatchFailure,
)
from local_actor_fixtures import case
from test_local_actor import dispatch
from retrieval_fixtures import reference


def test_wrong_worker_route_rejected_before_loading_or_marker(tmp_path: Path) -> None:
    c = case(tmp_path)
    binding = c.binding.model_copy(
        update={
            "resource": c.binding.resource.model_copy(
                update={"expected_resource_id": "foreign-session"}
            )
        }
    )
    model = RecordedLocalActorModel(
        c.root, binding, c.client, c.loop.store, c.loop.journal.controls, c.authority
    )
    with pytest.raises(OwnershipConflict, match="route"):
        model.validate(
            c.intent, control=c.loop.journal.controls.bind(c.intent.operation)
        )
    assert (
        c.loader.loads == 0 and len(c.channel.sent) == 1 and not list(c.root.iterdir())
    )


@pytest.mark.parametrize(
    "change",
    ["provider", "scope", "cleanup_zero", "cleanup_bool", "cleanup_over", "schema"],
)
def test_binding_rejects_wrong_resource_or_budget(tmp_path: Path, change: str) -> None:
    c = case(tmp_path)
    data = c.binding.model_dump()
    if change == "provider":
        data["resource"]["provider_id"] = "fixed-generator-worker"
    elif change == "scope":
        data["resource"].update(scope="attempt", attempt_id="attempt")
    elif change == "schema":
        data["spec_ref"]["content_schema"] = "generator-resource-spec/3"
    else:
        data["cleanup_seconds"] = {
            "cleanup_zero": 0,
            "cleanup_bool": True,
            "cleanup_over": 61,
        }[change]
    with pytest.raises(ValidationError):
        LocalActorBinding.model_validate(data)


@pytest.mark.parametrize(
    "fault", ["prompt_bound", "old_parameters", "extra_parameters", "noncanonical"]
)
def test_invalid_input_stops_before_model_load(tmp_path: Path, fault: str) -> None:
    c = case(tmp_path)
    intent = c.intent
    if fault == "prompt_bound":
        intent = intent.model_copy(
            update={
                "input_ref": intent.input_ref.model_copy(
                    update={"size_bytes": MAX_ACTOR_INPUT_BYTES + 1}
                )
            }
        )
    else:
        import json

        raw = c.loop.store.read(intent.parameters_ref)
        values = json.loads(raw)
        if fault == "old_parameters":
            values["schema_version"] = "local-generator-parameters/1"
        elif fault == "extra_parameters":
            values["repair"] = True
        changed = json.dumps(values).encode()
        ref = c.loop.store.put(
            changed,
            EvidenceMetadata(
                media_type="application/json",
                content_schema="model-parameters/1",
                visibility="private",
                producer="unit",
            ),
        )
        intent = intent.model_copy(update={"parameters_ref": ref})
    with pytest.raises((EvidenceIntegrityError, ValidationError)):
        c.model.validate(intent, control=c.loop.journal.controls.bind(intent.operation))
    assert c.loader.loads == 0 and not list(c.root.iterdir())


@pytest.mark.parametrize(
    "fault", ["missing_snapshot", "changed_binding", "changed_generation"]
)
def test_retained_marker_never_becomes_a_new_permission(
    tmp_path: Path, fault: str
) -> None:
    c = case(tmp_path)
    call = LocalActorCall(binding=c.binding, intent=c.intent)
    control = c.loop.journal.controls.bind(c.intent.operation)
    consume_call(c.root, call, control)
    if fault == "missing_snapshot":
        next(c.root.glob("*.local-actor-call.json")).unlink()
    elif fault == "changed_binding":
        call = call.model_copy(
            update={
                "binding": call.binding.model_copy(
                    update={
                        "model_binding_ref": reference(
                            {"changed": True}, "model-binding/1"
                        )
                    }
                )
            }
        )
    else:
        call = call.model_copy(
            update={
                "intent": call.intent.model_copy(update={"generation_id": "different"})
            }
        )
    with pytest.raises((EvidenceIntegrityError, OwnershipConflict)):
        consume_call(c.root, call, control)
    assert c.loader.session.calls == 0


def test_competing_original_callers_get_only_one_send_opportunity(
    tmp_path: Path,
) -> None:
    c = case(tmp_path)
    call = LocalActorCall(binding=c.binding, intent=c.intent)
    control = c.loop.journal.controls.bind(c.intent.operation)

    def compete() -> str:
        try:
            consume_call(c.root, call, control)
            return "first"
        except DispatchAlreadyCommitted:
            return "consumed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(compete) for _ in range(2)]
        assert sorted(f.result() for f in futures) == ["consumed", "first"]


def test_returned_exchange_records_under_independent_control_after_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = case(tmp_path)
    original = c.client.generate_exchange
    control = c.loop.journal.controls.bind(c.intent.operation)

    def stopped() -> float:
        raise OperationStopped("CANCELLED", c.intent.operation.operation_id)

    def generate(*args: Any) -> ActorWorkerExchange:
        actual = original(*args)
        monkeypatch.setattr(control, "checkpoint", stopped)
        return actual

    monkeypatch.setattr(c.client, "generate_exchange", generate)
    result = execute_actor_generation(
        dispatch(c), c.loop.journal, c.model, c.loop.journal.controls
    )
    assert result.project().generation is not None and c.loader.session.calls == 1
    assert len(c.authority.completed) == 1


def test_wrong_publication_ref_preserves_candidate_and_actual_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = case(tmp_path)
    original = c.loop.store.put
    foreign = reference({"foreign": True}, "actor-worker-command/1", store=c.loop.store)

    def put(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        if metadata.content_schema == "actor-worker-command/1":
            return foreign
        return original(raw, metadata, control, exchange_id=exchange_id)

    monkeypatch.setattr(c.loop.store, "put", put)
    with pytest.raises(ActorDispatchFailure) as caught:
        execute_actor_generation(
            dispatch(c), c.loop.journal, c.model, c.loop.journal.controls
        )
    from lab_generate_skill.adapters.models.local_actor import LocalActorUnconfirmed

    failure = caught.value.primary
    assert isinstance(failure, LocalActorUnconfirmed) and failure.exchange is not None
    assert len(failure.retained) == 2 and failure.retained[-1] == foreign
    assert failure.retained[0] != foreign and c.loader.session.calls == 1
