"""Mid-call stop and corrupted fact validation at original cleanup boundaries."""

from lab_generate_skill.ports.lifecycle import OperationControl

from pathlib import Path
import pytest
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from lab_generate_skill.adapters.storage.atomic_snapshot import SnapshotTransaction
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorSnapshot,
    LocalGeneratorFact,
)
from local_generator_fixtures import case


@pytest.mark.parametrize("phase", ["fact", "completed"])
def test_stop_after_known_fact_retains_identity_and_fresh_cleanup_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    c = case(tmp_path)
    original_control = c.controls.bind(c.operation)
    put, write = c.evidence.put, SnapshotTransaction.write

    def stopped() -> float:
        raise OperationStopped("CANCELLED", c.operation.operation_id)

    def stop_put(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        ref = put(raw, metadata, control=control)
        if phase == "fact" and metadata.content_schema == "local-generator-fact/1":
            monkeypatch.setattr(original_control, "checkpoint", stopped)
        return ref

    def stop_write(tx: SnapshotTransaction, raw: bytes) -> None:
        write(tx, raw)
        if (
            phase == "completed"
            and LocalGeneratorSnapshot.model_validate_json(raw).fact_ref is not None
        ):
            monkeypatch.setattr(original_control, "checkpoint", stopped)

    monkeypatch.setattr(c.evidence, "put", stop_put)
    monkeypatch.setattr(SnapshotTransaction, "write", stop_write)
    with pytest.raises(OperationStopped) as caught:
        c.adapter().generate(c.request, c.operation)
    observed = getattr(caught.value, "generator_execution")
    assert observed.fact_ref is not None
    assert c.evidence.read(observed.fact_ref)
    snapshot = c.adapter().inspect(c.request, c.cleanup)
    assert (snapshot.fact_ref is not None) == (phase == "completed")
    assert (
        c.adapter().reconcile(c.request, observed.fact_ref, c.cleanup)
        == observed.response_ref
    )
    assert c.engine.calls == 1


@pytest.mark.parametrize("mutation", ["text", "finish", "intent", "token", "canonical"])
def test_pending_fact_cannot_be_completed_using_inconsistent_bytes(
    tmp_path: Path, mutation: str
) -> None:
    c = case(tmp_path)
    c.authority.denied = "completion"
    with pytest.raises(OwnershipConflict) as caught:
        c.adapter().generate(c.request, c.operation)
    observed = getattr(caught.value, "generator_execution")
    fact = LocalGeneratorFact.model_validate_json(c.evidence.read(observed.fact_ref))
    c.authority.denied = ""
    if mutation in ("text", "finish", "token"):
        field, value = {
            "text": ("text", "other"),
            "finish": ("finish_reason", "length"),
            "token": ("prompt_tokens", 101),
        }[mutation]
        fact = fact.model_copy(
            update={"output": fact.output.model_copy(update={field: value})}
        )
    elif mutation == "intent":
        fact = fact.model_copy(
            update={"intent": fact.intent.model_copy(update={"request_id": "other"})}
        )
    raw = fact.model_dump_json(indent=2 if mutation == "canonical" else None).encode()
    ref = c.evidence.put(raw, local_metadata("local-generator-fact/1"))
    with pytest.raises((EvidenceIntegrityError, OwnershipConflict)):
        c.adapter().reconcile(c.request, ref, c.cleanup)
    assert c.adapter().inspect(c.request, c.cleanup).fact_ref is None
    assert c.engine.calls == 1
    assert (
        c.adapter().reconcile(c.request, observed.fact_ref, c.cleanup)
        == observed.response_ref
    )
