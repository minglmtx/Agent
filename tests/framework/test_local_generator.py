"""Durable local inference contracts and actual disk failure invariants."""

from lab_generate_skill.ports.lifecycle import OperationControl

from datetime import timedelta
from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.models.local_generator_state import invocation_file
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from lab_generate_skill.adapters.storage.atomic_snapshot import SnapshotTransaction
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorBaseParameters,
    LocalGeneratorSnapshot,
    LocalGeneratorFact,
    invocation_key,
)
from local_generator_fixtures import case, UnitEngine


def test_completed_reopen_reads_original_fact_without_engine(tmp_path: Path) -> None:
    c = case(tmp_path)
    ref = c.adapter().generate(c.request, c.operation)
    snapshot = c.adapter().inspect(c.request, c.cleanup)
    assert snapshot.response_ref == ref and snapshot.fact_ref is not None
    fact = LocalGeneratorFact.model_validate_json(c.evidence.read(snapshot.fact_ref))
    assert fact.output == c.engine.output and fact.intent.operation == c.operation
    assert (
        c.evidence.read(fact.intent.request_ref) == c.request.model_dump_json().encode()
    )
    c.engine = UnitEngine()
    c.engine.reject = True
    c.authority.denied = "generate"
    assert c.adapter().generate(c.request, c.operation) == ref
    assert c.adapter().reconcile(c.request, snapshot.fact_ref, c.cleanup) == ref
    assert c.engine.calls == c.engine.validations == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_input_tokens", 0),
        ("max_input_tokens", True),
        ("max_input_tokens", 1048577),
        ("max_new_tokens", -1),
        ("max_new_tokens", 65537),
        ("max_new_tokens", "1"),
        ("top_p", 0),
        ("top_p", float("nan")),
        ("top_p", 1.01),
        ("enable_thinking", 1),
        ("enable_thinking", None),
        ("unknown", 1),
    ],
)
def test_invalid_parameters_are_rejected(field: str, value: object) -> None:
    params: dict[str, object] = dict(
        max_input_tokens=100, max_new_tokens=100, top_p=0.95, enable_thinking=False
    )
    params[field] = value
    with pytest.raises(ValidationError):
        LocalGeneratorBaseParameters.model_validate(params)


@pytest.mark.parametrize(
    "failure", ["access", "generate", "preflight", "expired", "cleanup", "attempt"]
)
def test_preflight_denials_never_commit_intent_or_infer(
    tmp_path: Path, failure: str
) -> None:
    c = case(tmp_path)
    op = c.operation
    if failure in ("access", "generate"):
        c.authority.denied = failure
    elif failure == "preflight":
        c.engine.reject = True
    elif failure == "expired":
        op = op.model_copy(update={"deadline": op.deadline - timedelta(seconds=120)})
    elif failure == "cleanup":
        op = c.cleanup
    else:
        op = op.model_copy(update={"attempt_id": "attempt"})
    with pytest.raises((ValueError, OwnershipConflict, OperationStopped)):
        c.adapter().generate(c.request, op)
    assert c.engine.calls == 0
    assert all(p.name.endswith(".lock") for p in c.root.iterdir())


@pytest.mark.parametrize(
    "field",
    ["seed", "temperature", "messages", "operation", "owner", "model", "release"],
)
def test_same_identity_changed_input_or_binding_cannot_reexecute(
    tmp_path: Path, field: str
) -> None:
    c = case(tmp_path)
    c.adapter().generate(c.request, c.operation)
    original_key = invocation_key(c.binding, c.request.request_id)
    if field in ("seed", "temperature"):
        c.request = c.request.model_copy(update={field: 9 if field == "seed" else 0.4})
    elif field == "messages":
        c.request = c.request.model_copy(
            update={
                "messages": (
                    c.request.messages[0],
                    c.request.messages[1].model_copy(update={"content": "changed"}),
                )
            }
        )
    elif field == "operation":
        c.operation = c.operation.model_copy(update={"operation_id": "other"})
    elif field == "owner":
        c.binding = c.binding.model_copy(
            update={
                "owner": c.binding.owner.model_copy(update={"worker_id": "new-worker"})
            }
        )
    else:
        name, schema = (
            ("model_binding_ref", "model-binding/1")
            if field == "model"
            else ("release_ref", "release-manifest/1")
        )
        c.binding = c.binding.model_copy(
            update={name: c.evidence.put(b"changed", local_metadata(schema))}
        )
    assert invocation_key(c.binding, c.request.request_id) == original_key
    with pytest.raises(OwnershipConflict):
        c.adapter().generate(c.request, c.operation)
    assert c.engine.calls == 1


def test_engine_failure_keeps_pending_and_original_exception(tmp_path: Path) -> None:
    c = case(tmp_path)
    error = ExceptionGroup("model and cleanup", [ValueError("model"), OSError("close")])
    c.engine.failure = error
    with pytest.raises(ExceptionGroup) as caught:
        c.adapter().generate(c.request, c.operation)
    assert caught.value is error
    observed = getattr(error, "generator_execution")
    assert observed.intent.operation == c.operation and observed.fact_ref is None
    assert c.adapter().inspect(c.request, c.cleanup).fact_ref is None
    with pytest.raises(DispatchAlreadyCommitted):
        c.adapter().generate(c.request, c.operation)
    assert c.engine.calls == 1


@pytest.mark.parametrize("fault", ["response", "fact", "snapshot", "authority"])
def test_saved_facts_allow_only_explicit_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = case(tmp_path)
    real_put, real_write = c.evidence.put, SnapshotTransaction.write
    error = OSError("committed but acknowledgement lost")

    def put(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        ref = real_put(raw, metadata)
        if metadata.content_schema == {
            "response": "generator-model-response/1",
            "fact": "local-generator-fact/1",
        }.get(fault):
            raise error
        return ref

    def write(tx: SnapshotTransaction, raw: bytes) -> None:
        snapshot = LocalGeneratorSnapshot.model_validate_json(raw)
        if snapshot.fact_ref is not None and fault == "snapshot":
            raise error
        real_write(tx, raw)

    monkeypatch.setattr(c.evidence, "put", put)
    monkeypatch.setattr(SnapshotTransaction, "write", write)
    if fault == "authority":
        c.authority.denied = "completion"
    with pytest.raises((OSError, OwnershipConflict)) as caught:
        c.adapter().generate(c.request, c.operation)
    observed = getattr(caught.value, "generator_execution")
    assert observed.fact_ref is not None and observed.completion is not None
    assert c.adapter().inspect(c.request, c.cleanup).fact_ref is None
    with pytest.raises(DispatchAlreadyCommitted):
        c.adapter().generate(c.request, c.operation)
    monkeypatch.setattr(c.evidence, "put", real_put)
    monkeypatch.setattr(SnapshotTransaction, "write", real_write)
    c.authority.denied = ""
    if fault == "response":
        # The fact did not reach CAS. An expected hash is not a saved fact.
        with pytest.raises(EvidenceNotFound):
            c.adapter().reconcile(c.request, observed.fact_ref, c.cleanup)
        assert c.adapter().inspect(c.request, c.cleanup).fact_ref is None
    else:
        assert (
            c.adapter().reconcile(c.request, observed.fact_ref, c.cleanup)
            == observed.response_ref
        )
        assert (
            c.adapter().reconcile(c.request, observed.fact_ref, c.cleanup)
            == observed.response_ref
        )
    assert c.engine.calls == 1


@pytest.mark.parametrize(
    "missing", ["snapshot", "marker", "birth", "lock", "snapshot_and_marker"]
)
def test_lost_history_is_never_empty_reinitialization(
    tmp_path: Path, missing: str
) -> None:
    c = case(tmp_path)
    c.adapter().generate(c.request, c.operation)
    name = invocation_file(c.root, c.binding, c.request.request_id).name
    paths = {
        "snapshot": [name],
        "marker": [name + ".initialized"],
        "birth": [name + ".pending-" + "0" * 64],
        "lock": [name + ".lock"],
        "snapshot_and_marker": [name, name + ".initialized"],
    }
    for path in paths[missing]:
        (c.root / path).unlink()
    before = {p.name: p.read_bytes() for p in c.root.iterdir()}
    with pytest.raises(EvidenceIntegrityError):
        c.adapter().generate(c.request, c.operation)
    assert {p.name: p.read_bytes() for p in c.root.iterdir()} == before
    assert c.engine.calls == 1


@pytest.mark.parametrize("tokens", ["prompt_tokens", "completion_tokens"])
def test_out_of_budget_output_saved_but_cannot_complete(
    tmp_path: Path, tokens: str
) -> None:
    c = case(tmp_path)
    c.engine.output = c.engine.output.model_copy(update={tokens: 101})
    with pytest.raises(EvidenceIntegrityError) as caught:
        c.adapter().generate(c.request, c.operation)
    observed = getattr(caught.value, "generator_execution")
    assert c.evidence.read(observed.fact_ref)
    with pytest.raises(EvidenceIntegrityError):
        c.adapter().reconcile(c.request, observed.fact_ref, c.cleanup)
    assert c.adapter().inspect(c.request, c.cleanup).fact_ref is None
    assert c.engine.calls == 1


def test_wrong_parent_and_replacement_fact_rejected(tmp_path: Path) -> None:
    c = case(tmp_path)
    c.adapter().generate(c.request, c.operation)
    snapshot = c.adapter().inspect(c.request, c.cleanup)
    assert snapshot.fact_ref is not None
    with pytest.raises(OwnershipConflict):
        c.adapter().reconcile(
            c.request,
            snapshot.fact_ref,
            c.cleanup.model_copy(
                update={"operation_id": "wrong-parent", "parent_operation_id": "other"}
            ),
        )
    fact = LocalGeneratorFact.model_validate_json(c.evidence.read(snapshot.fact_ref))
    other = fact.model_copy(
        update={"output": fact.output.model_copy(update={"prompt_tokens": 11})}
    )
    ref = c.evidence.put(
        other.model_dump_json().encode(), local_metadata("local-generator-fact/1")
    )
    with pytest.raises(OwnershipConflict):
        c.adapter().reconcile(c.request, ref, c.cleanup)
    assert c.adapter().inspect(c.request, c.cleanup) == snapshot


@pytest.mark.parametrize("failure", ["birth", "intent"])
def test_failed_intent_commit_never_calls_engine_or_reinitializes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    c = case(tmp_path)
    write, retain = SnapshotTransaction.write, SnapshotTransaction.retain_pending
    error = OSError("intent confirmation lost")

    def bad_write(tx: SnapshotTransaction, raw: bytes) -> None:
        write(tx, raw)
        raise error

    def bad_retain(tx: SnapshotTransaction, key: str, raw: bytes) -> None:
        retain(tx, key, raw)
        raise error

    monkeypatch.setattr(
        SnapshotTransaction,
        "write" if failure == "intent" else "retain_pending",
        bad_write if failure == "intent" else bad_retain,
    )
    with pytest.raises(OSError) as caught:
        c.adapter().generate(c.request, c.operation)
    assert caught.value is error and c.engine.calls == 0
    monkeypatch.setattr(SnapshotTransaction, "write", write)
    monkeypatch.setattr(SnapshotTransaction, "retain_pending", retain)
    with pytest.raises((EvidenceIntegrityError, DispatchAlreadyCommitted)):
        c.adapter().generate(c.request, c.operation)
    assert c.engine.calls == 0


@pytest.mark.parametrize("target", ["base", "fact", "response"])
def test_corrupt_evidence_fails_without_reexecution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    c = case(tmp_path)
    c.adapter().generate(c.request, c.operation)
    schema = {
        "base": "model-parameters/1",
        "fact": "local-generator-fact/1",
        "response": "generator-model-response/1",
    }[target]
    read = c.evidence.read

    def damaged(ref: EvidenceRef, control: OperationControl | None = None) -> bytes:
        return b"corrupt" if ref.content_schema == schema else read(ref)

    monkeypatch.setattr(c.evidence, "read", damaged)
    with pytest.raises(EvidenceIntegrityError):
        c.adapter().generate(c.request, c.operation)
    assert c.engine.calls == 1


@pytest.mark.parametrize(
    "text,finish", [("", "stop"), ("非法 {", "stop"), ("部分", "length")]
)
def test_invalid_skill_is_retained_as_original_model_fact(
    tmp_path: Path, text: str, finish: str
) -> None:
    c = case(tmp_path)
    c.engine.output = c.engine.output.model_copy(
        update={"text": text, "finish_reason": finish}
    )
    ref = c.adapter().generate(c.request, c.operation)
    assert c.adapter().generate(c.request, c.operation) == ref
    snapshot = c.adapter().inspect(c.request, c.cleanup)
    assert snapshot.fact_ref is not None
    fact = LocalGeneratorFact.model_validate_json(c.evidence.read(snapshot.fact_ref))
    assert fact.output.text == text and fact.output.finish_reason == finish
    assert c.engine.calls == 1


def test_parameter_and_output_boundaries(tmp_path: Path) -> None:
    c = case(tmp_path)
    base = LocalGeneratorBaseParameters(
        max_input_tokens=1, max_new_tokens=1, top_p=1.0, enable_thinking=True
    )
    c.binding = c.binding.model_copy(
        update={
            "base_parameters_ref": c.evidence.put(
                base.model_dump_json().encode(), local_metadata("model-parameters/1")
            )
        }
    )
    c.request = c.request.model_copy(update={"seed": 2147483647, "temperature": 0.0})
    c.engine.output = c.engine.output.model_copy(
        update={"prompt_tokens": 1, "completion_tokens": 1}
    )
    assert c.adapter().generate(c.request, c.operation)
    assert c.engine.calls == 1


def test_missing_original_read_is_side_effect_free(tmp_path: Path) -> None:
    c = case(tmp_path)
    with pytest.raises(EvidenceIntegrityError):
        c.adapter().inspect(c.request, c.cleanup)
    assert list(c.root.iterdir()) == []
