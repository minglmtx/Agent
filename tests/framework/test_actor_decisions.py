"""Original response binding, actual parse failures and evidence-I/O faults."""

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.actor.decisions import RecordedActorDecisions
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.domain.actor_generation import ActorGeneration
from lab_generate_skill.domain.actor_response import (
    ActorTextCompletion,
    ActorParseFailure,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from evidence_control_fixtures import EvidenceFixtureStore
from trace_journal_fixtures import fixture, LiveTraceFixture
from retrieval_fixtures import reference
from test_run_journal import command
from test_actor_protocol import turn


def prepared(
    root: Path, text: str = '{"action":"click(\'2\')"}', finish: str = "stop"
) -> tuple[
    LiveTraceFixture, ActorGeneration, ActorTextCompletion, RecordedActorDecisions
]:
    data = fixture(root, outcomes=("returned",))
    prompt = prepare_actor(turn())
    input_ref = reference(prompt, "actor-model-input/1", store=data.store)
    old = data.data.trace.turns[0].generation
    completion = ActorTextCompletion(
        generation_id=old.generation_id,
        request_id=old.request_id,
        input_ref=input_ref,
        parameters_ref=old.parameters_ref,
        model_input_sha256=hashlib.sha256(prompt.input_bytes()).hexdigest(),
        text=text,
        finish_reason=finish,
    )
    response = reference(completion, "actor-model-response/1", store=data.store)
    generation = old.model_copy(
        update={"input_ref": input_ref, "response_ref": response}
    )
    return (
        data,
        generation,
        completion,
        RecordedActorDecisions(data.store, data.journal().controls),
    )


def parse_op() -> OperationContext:
    return command("parse-response", attempt="attempt")


def test_actual_saved_response_yields_stable_action_without_new_effects(
    tmp_path: Path,
) -> None:
    data, generation, _, decisions = prepared(tmp_path)
    before = set((data.root / "evidence/blobs").iterdir())
    operation = parse_op()
    result = decisions.decide(generation, turn().task, operation)
    assert result.outcome == "action" and result.action is not None
    assert result.action.payload == "click('2')"
    assert result.generation_id == generation.generation_id
    assert decisions.decide(generation, turn().task, operation) == result
    assert set((data.root / "evidence/blobs").iterdir()) == before


@pytest.mark.parametrize(
    "text,finish",
    [
        ("", "stop"),
        ("invalid", "stop"),
        ('{"action":"click(\'2\')"}', "length"),
        ('{"action":"goto(\'https://bad.example/\')"}', "stop"),
    ],
)
def test_invalid_completed_output_stores_original_parse_failure(
    tmp_path: Path, text: str, finish: str
) -> None:
    data, generation, _, decisions = prepared(tmp_path, text, finish)
    result = decisions.decide(generation, turn().task, parse_op())
    assert (
        result.outcome == "invalid"
        and result.action is None
        and result.failure_ref is not None
    )
    failure = ActorParseFailure.model_validate_json(data.store.read(result.failure_ref))
    assert (
        failure.response_ref == generation.response_ref
        and failure.generation_id == generation.generation_id
    )
    assert failure.reason_code == "INVALID_ACTOR_RESPONSE"


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation_id", "other"),
        ("request_id", "other"),
        ("model_input_sha256", "0" * 64),
    ],
)
def test_wrong_completion_binding_is_integrity_failure_not_invalid_choice(
    tmp_path: Path, field: str, value: str
) -> None:
    data, generation, completion, decisions = prepared(tmp_path)
    changed = completion.model_copy(update={field: value})
    generation = generation.model_copy(
        update={
            "response_ref": reference(
                changed, "actor-model-response/1", store=data.store
            )
        }
    )
    with pytest.raises(OwnershipConflict):
        decisions.decide(generation, turn().task, parse_op())


@pytest.mark.parametrize("which", ["input_ref", "parameters_ref"])
def test_completion_cannot_substitute_actual_input_or_parameters(
    tmp_path: Path, which: str
) -> None:
    data, generation, completion, decisions = prepared(tmp_path)
    current = getattr(completion, which)
    changed = completion.model_copy(
        update={which: current.model_copy(update={"producer": "other"})}
    )
    generation = generation.model_copy(
        update={
            "response_ref": reference(
                changed, "actor-model-response/1", store=data.store
            )
        }
    )
    with pytest.raises(OwnershipConflict):
        decisions.decide(generation, turn().task, parse_op())


@pytest.mark.parametrize("which", ["input_ref", "parameters_ref", "response_ref"])
def test_missing_actual_bytes_propagate_without_parse_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    data, generation, _, decisions = prepared(tmp_path)
    read = data.store.read

    def missing(ref: EvidenceRef, control: OperationControl | None = None) -> bytes:
        if ref == getattr(generation, which):
            raise FileNotFoundError("original bytes missing")
        return read(ref, control)

    monkeypatch.setattr(data.store, "read", missing)
    with pytest.raises(FileNotFoundError):
        decisions.decide(generation, turn().task, parse_op())


def test_reader_corruption_does_not_become_invalid_model_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data, generation, _, decisions = prepared(tmp_path)
    monkeypatch.setattr(data.store, "read", lambda ref, control=None: b"{}")
    with pytest.raises(EvidenceIntegrityError):
        decisions.decide(generation, turn().task, parse_op())


def test_noncanonical_original_completion_is_not_an_invalid_choice(
    tmp_path: Path,
) -> None:
    data, generation, completion, decisions = prepared(tmp_path)
    raw = (completion.model_dump_json() + "\n").encode()
    assert generation.response_ref is not None
    ref = data.store.put(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="actor-model-response/1",
            visibility="private",
            producer="unit-response",
        ),
    )
    with pytest.raises(EvidenceIntegrityError, match="canonical"):
        decisions.decide(
            generation.model_copy(update={"response_ref": ref}), turn().task, parse_op()
        )


def test_expired_parse_control_performs_no_evidence_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.domain.errors import OperationStopped

    data, generation, _, decisions = prepared(tmp_path)

    def read(ref: EvidenceRef, control: OperationControl | None = None) -> bytes:
        raise AssertionError("Expired operation must stop before evidence access")

    monkeypatch.setattr(data.store, "read", read)
    op = parse_op().model_copy(
        update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
    )
    with pytest.raises(OperationStopped):
        decisions.decide(generation, turn().task, op)


def test_wrong_publication_return_preserves_actual_returned_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data, generation, _, decisions = prepared(tmp_path, "invalid")
    put = data.store.put
    returned: list[EvidenceRef] = []

    def wrong(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        result = put(raw, metadata, control, exchange_id=exchange_id).model_copy(
            update={"producer": "changed"}
        )
        returned.append(result)
        return result

    monkeypatch.setattr(data.store, "put", wrong)
    with pytest.raises(EvidenceIntegrityError) as caught:
        decisions.decide(generation, turn().task, parse_op())
    assert getattr(caught.value, "actor_parse_failure_reference") == returned[0]
    assert getattr(caught.value, "actor_generation") == generation


@pytest.mark.parametrize(
    "change", ["owner", "task", "same_operation", "cleanup_parent", "incomplete"]
)
def test_wrong_scope_or_phase_is_rejected_before_parsing(
    tmp_path: Path, change: str
) -> None:
    data, generation, _, decisions = prepared(tmp_path)
    task, op = turn().task, parse_op()
    if change == "owner":
        op = op.model_copy(update={"owner_id": "other"})
    if change == "task":
        task = task.model_copy(
            update={"identity": task.identity.model_copy(update={"task_id": "other"})}
        )
    if change == "same_operation":
        op = generation.operation
    if change == "cleanup_parent":
        op = op.model_copy(update={"mode": "cleanup", "parent_operation_id": "other"})
    if change == "incomplete":
        generation = generation.model_copy(
            update={
                "status": "uncertain",
                "response_ref": None,
                "failure_ref": reference(
                    {"lost": True}, "generation-failure/1", store=data.store
                ),
            }
        )
    with pytest.raises((OwnershipConflict, ValueError)):
        decisions.decide(generation, task, op)


@pytest.mark.parametrize("committed", [False, True])
def test_unknown_parse_failure_publication_retains_original_and_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, committed: bool
) -> None:
    data, generation, _, decisions = prepared(tmp_path, "invalid")
    put = data.store.put

    def lost(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        if committed:
            put(raw, metadata, control, exchange_id=exchange_id)
        raise OSError("lost acknowledgement")

    monkeypatch.setattr(data.store, "put", lost)
    with pytest.raises(OSError) as caught:
        decisions.decide(generation, turn().task, parse_op())
    assert getattr(caught.value, "actor_generation") == generation
    candidate = cast(
        EvidenceRef, getattr(caught.value, "actor_parse_failure_candidate")
    )
    assert getattr(caught.value, "actor_parse_failure_reference") is None
    if committed:
        assert (
            ActorParseFailure.model_validate_json(
                data.store.read(candidate)
            ).response_ref
            == generation.response_ref
        )


@pytest.mark.parametrize("value", [None, "", 1, [], ()])
def test_wrong_generation_type_rejected(tmp_path: Path, value: object) -> None:
    _, _, _, decisions = prepared(tmp_path)
    with pytest.raises(ValueError):
        decisions.decide(cast(ActorGeneration, value), turn().task, parse_op())
