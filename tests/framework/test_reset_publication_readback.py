"""Same-call Reset proof/readback, fresh authority and independent revalidation."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.domain.reset import ResetReceipt
from lab_generate_skill.domain.state_scope import StateCommitUnconfirmed
from lab_generate_skill.ports.lifecycle import OperationControl
from state_storage_fixtures import fixture


def test_reset_publication_one_graph_two_authorities_and_later_fresh_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = fixture(tmp_path)
    original = c.adapter.resets.verify
    graphs: list[ResetReceipt] = []

    def verify(receipt: ResetReceipt, control: OperationControl) -> Any:
        graphs.append(receipt)
        return original(receipt, control)

    monkeypatch.setattr(c.adapter.resets, "verify", verify)
    ref = c.adapter.publish_reset_verified(c.reset, c.reset.operation)
    assert graphs == [c.reset] and c.authority.calls == ["reset", "reset"]
    assert c.store.read(ref) == c.reset.model_dump_json().encode()
    assert c.adapter.load_reset(ref, c.reset.operation) == c.reset
    assert graphs == [c.reset, c.reset] and len(c.authority.calls) == 3
    c.authority.denied = True
    with pytest.raises(OwnershipConflict):
        c.adapter.load_reset(ref, c.reset.operation)
    assert len(graphs) == 3


@pytest.mark.parametrize("fault", ["readback", "different-summary", "authority"])
def test_reset_returned_reference_survives_readback_or_revocation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = fixture(tmp_path)
    original_read, original_verify = c.store.read, c.authority.verify_reset
    first = OSError("original reset readback failed")

    def read(reference: EvidenceRef, control: OperationControl | None = None) -> bytes:
        if reference.content_schema == "reset-receipt/1":
            if fault == "readback":
                raise first
            if fault == "different-summary":
                return (
                    c.reset.model_copy(update={"status": "quarantined"})
                    .model_dump_json()
                    .encode()
                )
        return original_read(reference, control=control)

    def verify(*args: Any) -> None:
        if fault == "authority" and len(c.authority.calls) == 1:
            c.authority.denied = True
        original_verify(*args)

    monkeypatch.setattr(c.store, "read", read)
    monkeypatch.setattr(c.authority, "verify_reset", verify)
    with pytest.raises(StateCommitUnconfirmed) as caught:
        c.adapter.publish_reset_verified(c.reset, c.reset.operation)
    assert original_read(caught.value.reference) == c.reset.model_dump_json().encode()
    assert (
        caught.value.__cause__ is first
        if fault == "readback"
        else isinstance(caught.value.__cause__, OwnershipConflict)
    )


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_reset_full_transitive_protection_remains_before_publication(
    tmp_path: Path, fault: str
) -> None:
    c = fixture(tmp_path)
    path = tmp_path / "blobs" / c.protected_ref.sha256
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"corrupt original dependency")
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(
        EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
    ):
        c.adapter.publish_reset_verified(c.reset, c.reset.operation)
    assert set((tmp_path / "blobs").iterdir()) == before and not c.authority.calls


@pytest.mark.parametrize("bad", [None, "", [], {}, True, 0])
def test_invalid_reset_summary_never_reaches_graph_or_write(
    tmp_path: Path, bad: Any
) -> None:
    c = fixture(tmp_path)
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises((ValueError, TypeError)):
        c.adapter.publish_reset_verified(bad, c.reset.operation)
    assert set((tmp_path / "blobs").iterdir()) == before and not c.authority.calls


def test_reset_transport_scope_refused_before_write(tmp_path: Path) -> None:
    c = fixture(tmp_path)
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(OwnershipConflict):
        c.adapter.publish_reset_verified(
            c.reset, c.reset.operation.model_copy(update={"owner_id": "foreign-owner"})
        )
    assert set((tmp_path / "blobs").iterdir()) == before and not c.authority.calls


def test_reset_post_commit_cancel_preserves_saved_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = fixture(tmp_path)
    operation = c.reset.operation.model_copy(
        update={
            "cancellation_ref": CancellationRef(
                channel_id="cancel", run_id="run", owner_id="owner"
            )
        }
    )
    receipt = c.reset.model_copy(update={"operation": operation})
    original = c.store.put

    def put(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        ref = original(raw, metadata, control=control)
        c.switch.cancelled = True
        return ref

    with monkeypatch.context() as patch:
        patch.setattr(c.store, "put", put)
        with pytest.raises(StateCommitUnconfirmed) as caught:
            c.adapter.publish_reset_verified(receipt, operation)
    assert isinstance(caught.value.__cause__, OperationStopped)
    assert c.store.read(caught.value.reference) == receipt.model_dump_json().encode()
