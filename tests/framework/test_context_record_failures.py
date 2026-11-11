"""Qualification publication faults, cancellation and historical reconciliation."""

from lab_generate_skill.ports.lifecycle import OperationControl

from datetime import timedelta
from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import CancellationRef, OperationContext
from lab_generate_skill.domain.public_context import (
    ContextCommitUnconfirmed,
    PublicContextInputs,
    PublicContextReceipt,
)
from lab_generate_skill.runtime.lifecycle import OperationGuards
from context_storage_fixtures import fixture
from test_lifecycle import ManualClock
from test_run_journal import command


@pytest.mark.parametrize("kind", ["context", "equivalence"])
@pytest.mark.parametrize("committed", [False, True])
def test_put_failure_preserves_first_and_cleanup_errors_and_actual_disk_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, committed: bool
) -> None:
    data = fixture(tmp_path)
    original = data.candidate(kind)
    candidate = original.model_copy(
        update={
            "operation": original.operation.model_copy(
                update={"operation_id": "fresh-publication"}
            )
        }
    )
    put = data.store.put
    error = ExceptionGroup(
        "commit and cleanup", [OSError("commit"), OSError("cleanup")]
    )

    def fail(
        value: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
    ) -> EvidenceRef:
        if committed:
            put(value, metadata)
        raise error

    before = set((tmp_path / "blobs").iterdir())
    with monkeypatch.context() as patch:
        patch.setattr(data.store, "put", fail)
        with pytest.raises(ExceptionGroup) as caught:
            data.publish(candidate, candidate.operation)
    assert caught.value is error
    assert len(set((tmp_path / "blobs").iterdir()) - before) == int(committed)
    ref = data.publish(candidate, candidate.operation)
    assert data.load(kind, ref, command()) == candidate
    assert len(set((tmp_path / "blobs").iterdir()) - before) == 1


@pytest.mark.parametrize("kind", ["context", "equivalence"])
def test_postcommit_cancellation_retains_reference_and_cleanup_can_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    operation = candidate.operation.model_copy(
        update={
            "cancellation_ref": CancellationRef(
                channel_id="cancel", run_id="run", owner_id="owner"
            )
        }
    )
    candidate = candidate.model_copy(update={"operation": operation})
    put = data.store.put

    def cancel(
        value: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
    ) -> EvidenceRef:
        ref = put(value, metadata)
        data.switch.cancelled = True
        return ref

    with monkeypatch.context() as patch:
        patch.setattr(data.store, "put", cancel)
        with pytest.raises(ContextCommitUnconfirmed) as caught:
            data.publish(candidate, operation)
    assert isinstance(caught.value.__cause__, OperationStopped)
    ref = caught.value.reference
    assert data.store.read(ref) == candidate.model_dump_json().encode()
    cleanup = operation.cleanup("reconcile", now=command().deadline, seconds=30)
    assert data.load(kind, ref, cleanup) == candidate
    assert data.publish(candidate, cleanup) == ref


@pytest.mark.parametrize("kind", ["context", "equivalence"])
def test_expired_original_reconciles_without_rewriting_deadline(
    tmp_path: Path, kind: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    expired = candidate.operation.model_copy(
        update={"deadline": candidate.operation.deadline - timedelta(days=1)}
    )
    candidate = candidate.model_copy(update={"operation": expired})
    with pytest.raises(OperationStopped):
        data.publish(candidate, expired)
    cleanup = expired.cleanup("reconcile", now=command().deadline, seconds=30)
    ref = data.publish(candidate, cleanup)
    assert data.load(kind, ref, cleanup) == candidate
    assert data.store.read(ref) == candidate.model_dump_json().encode()


@pytest.mark.parametrize("kind", ["context", "equivalence"])
def test_authority_timeout_stops_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    data = fixture(tmp_path)
    clock = ManualClock()
    data.adapter.controls = OperationGuards(clock, data.switch)
    candidate = data.candidate(kind)
    operation = candidate.operation.model_copy(
        update={"deadline": clock.utcnow() + timedelta(seconds=1)}
    )
    candidate = candidate.model_copy(update={"operation": operation})
    original = data.authority.verify_context

    def slow(
        inputs: PublicContextInputs, receipt: PublicContextReceipt, op: OperationContext
    ) -> None:
        original(inputs, receipt, op)
        clock.sleep(2)

    monkeypatch.setattr(data.authority, "verify_context", slow)
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(OperationStopped):
        data.publish(candidate, operation)
    assert set((tmp_path / "blobs").iterdir()) == before


@pytest.mark.parametrize("kind", ["context", "equivalence"])
@pytest.mark.parametrize("field", ["run_id", "owner_id"])
def test_read_wrong_owner_rejected_before_authority(
    tmp_path: Path, kind: str, field: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    ref = data.publish(candidate, candidate.operation)
    data.authority.calls.clear()
    with pytest.raises(OwnershipConflict):
        data.load(kind, ref, command().model_copy(update={field: "other"}))
    assert data.authority.calls == []


def test_comparison_read_wrong_attempt_is_not_source_cross_attempt_permission(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    ref = data.publish(data.comparison, data.comparison.operation)
    data.authority.calls.clear()
    with pytest.raises(OwnershipConflict):
        data.load("equivalence", ref, command(attempt="other"))
    assert data.authority.calls == []


@pytest.mark.parametrize("kind", ["context", "equivalence"])
@pytest.mark.parametrize("fault", ["visibility", "schema"])
def test_read_root_reference_contract(tmp_path: Path, kind: str, fault: str) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    ref = data.publish(candidate, candidate.operation)
    changes = (
        {"visibility": "public"}
        if fault == "visibility"
        else {"content_schema": "obsolete/1"}
    )
    data.authority.calls.clear()
    with pytest.raises(ValueError):
        data.load(kind, ref.model_copy(update=changes), command())
    assert data.authority.calls == []
