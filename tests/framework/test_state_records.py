"""Actual baseline/reset bytes: recomputation, permissions, faults and closure."""

from lab_generate_skill.ports.lifecycle import OperationControl

from datetime import timedelta
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.baseline import BaselineReceipt, BaselineInputs
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import CancellationRef, OperationContext
from lab_generate_skill.domain.reset import ResetReceipt, ResetInputs
from lab_generate_skill.domain.state_scope import StateCommitUnconfirmed
from lab_generate_skill.runtime.lifecycle import OperationGuards
from state_storage_fixtures import fixture, UnitStateAuthority
from test_lifecycle import ManualClock
from test_run_journal import command
from retrieval_fixtures import reference


@pytest.mark.parametrize("kind", ["baseline", "reset"])
def test_publish_repeat_load_reverifies_actual_graph_and_authority(
    tmp_path: Path, kind: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    ref = data.publish(candidate, candidate.operation)
    assert data.publish(candidate, candidate.operation) == ref
    assert data.load(kind, ref, command()) == candidate
    assert (
        data.load(kind, ref, command(attempt="attempt", cleanup_parent="read-only"))
        == candidate
    )
    assert data.authority.calls == [kind] * 4
    assert data.store.read(ref) == candidate.model_dump_json().encode()


@pytest.mark.parametrize("kind", ["baseline", "reset"])
def test_mandatory_authority_on_both_boundaries(tmp_path: Path, kind: str) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    ref = data.publish(candidate, candidate.operation)
    data.authority.denied = True
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(OwnershipConflict):
        data.publish(candidate, candidate.operation)
    with pytest.raises(OwnershipConflict):
        data.load(kind, ref, command())
    assert set((tmp_path / "blobs").iterdir()) == before


@pytest.mark.parametrize("kind", ["baseline", "reset"])
@pytest.mark.parametrize("change", ["status", "scope", "summary_field"])
def test_forged_summary_rejected_in_publish_and_consume(
    tmp_path: Path, kind: str, change: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    if change == "status":
        candidate = candidate.model_copy(
            update={"status": "unknown" if kind == "baseline" else "quarantined"}
        )
    elif change == "scope":
        candidate = candidate.model_copy(
            update={"scope": candidate.scope.model_copy(update={"context_id": "other"})}
        )
    elif isinstance(candidate, BaselineReceipt):
        candidate = candidate.model_copy(update={"measured_state_sha256": "f" * 64})
    else:
        candidate = candidate.model_copy(
            update={"health_ref": reference({}, "reset-health/1", store=data.store)}
        )
    ref = reference(candidate, candidate.schema_version, store=data.store)
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises((ValueError, OwnershipConflict)):
        data.publish(candidate, candidate.operation)
    with pytest.raises((ValueError, OwnershipConflict)):
        data.load(kind, ref, command())
    assert set((tmp_path / "blobs").iterdir()) == before


@pytest.mark.parametrize("kind", ["baseline", "reset"])
@pytest.mark.parametrize("fault", ["missing", "corrupt"])
@pytest.mark.parametrize(
    "item",
    ["spec", "phase", "private_fact", "recovery", "protected", "original_baseline"],
)
def test_transitive_bytes_not_just_reference_metadata(
    tmp_path: Path, kind: str, fault: str, item: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    ref = data.publish(candidate, candidate.operation)
    b, r = data.baseline_inputs, data.reset_inputs
    targets = {
        "spec": b.spec_ref if kind == "baseline" else r.plan.spec_ref,
        "phase": b.prepared_ref if kind == "baseline" else r.task_ref,
        "private_fact": (
            b.initial.checks.checks[0].evidence[0]
            if kind == "baseline"
            else r.health.checks.checks[0].evidence[0]
        ),
        "recovery": (
            b.prepared.recovery_ref if kind == "baseline" else r.plan.task_recovery_ref
        ),
        "protected": data.protected_ref,
        "original_baseline": r.task_recovery.baseline_ref,
    }
    path = tmp_path / "blobs" / targets[item].sha256
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"corrupted")
    error = EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(error):
        data.load(kind, ref, command())
    with pytest.raises(error):
        data.publish(candidate, candidate.operation)
    assert set((tmp_path / "blobs").iterdir()) == before


@pytest.mark.parametrize("kind", ["baseline", "reset"])
def test_changed_actual_check_cannot_retain_ready_or_safe(
    tmp_path: Path, kind: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    fact = (
        data.baseline_inputs.initial if kind == "baseline" else data.reset_inputs.health
    )
    failed = fact.checks.checks[0].model_copy(update={"status": "fail"})
    fact = fact.model_copy(
        update={
            "checks": fact.checks.model_copy(
                update={"checks": (failed, *fact.checks.checks[1:])}
            )
        }
    )
    changed_ref = reference(fact, fact.schema_version, store=data.store)
    candidate = candidate.model_copy(
        update={
            "initial_checks_ref" if kind == "baseline" else "health_ref": changed_ref
        }
    )
    with pytest.raises(OwnershipConflict, match="summary differs"):
        data.publish(candidate, candidate.operation)
    # Correct diagnostic classification can be stored; it is not lost as an error.
    candidate = candidate.model_copy(
        update={"status": "rejected" if kind == "baseline" else "quarantined"}
    )
    ref = data.publish(candidate, candidate.operation)
    assert data.load(kind, ref, command()) == candidate


@pytest.mark.parametrize("kind", ["baseline", "reset"])
@pytest.mark.parametrize(
    "change",
    [
        "owner",
        "run",
        "attempt",
        "run_publish",
        "new_execute",
        "wrong_parent",
        "allocation",
        "recovery",
    ],
)
def test_wrong_transport_operation_has_no_writes(
    tmp_path: Path, kind: str, change: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    op = candidate.operation
    updates: dict[str, dict[str, object]] = {
        "owner": {"owner_id": "other"},
        "run": {"run_id": "other"},
        "attempt": {"attempt_id": "other"},
        "run_publish": {"attempt_id": None},
        "new_execute": {
            "operation_id": "new",
            "mode": "execute",
            "parent_operation_id": None,
        },
        "wrong_parent": {
            "operation_id": "new",
            "mode": "cleanup",
            "parent_operation_id": "wrong",
        },
    }
    updates["allocation"] = {
        "operation_id": "new",
        "mode": "cleanup",
        "parent_operation_id": op.operation_id,
        "allocation_id": "other",
    }
    updates["recovery"] = {
        "operation_id": "new",
        "mode": "cleanup",
        "parent_operation_id": op.operation_id,
        "recovery_ref": reference({}, "recovery-plan/1", store=data.store),
    }
    op = op.model_copy(update=updates[change])
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(OwnershipConflict):
        data.publish(candidate, op)
    assert set((tmp_path / "blobs").iterdir()) == before


@pytest.mark.parametrize("kind", ["baseline", "reset"])
def test_expired_original_reconciles_with_new_cleanup_without_rewriting_facts(
    tmp_path: Path, kind: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    clock = ManualClock()
    clock.wall = candidate.operation.deadline - timedelta(seconds=1)
    data.adapter.controls = OperationGuards(clock, data.switch)
    ref = data.publish(candidate, candidate.operation)
    before = data.store.read(ref)
    clock.sleep(2)
    with pytest.raises(OperationStopped):
        data.publish(candidate, candidate.operation)
    cleanup = candidate.operation.cleanup("reconcile", now=clock.utcnow(), seconds=10)
    assert data.publish(candidate, cleanup) == ref
    assert data.load(kind, ref, cleanup) == candidate
    assert data.store.read(ref) == before


@pytest.mark.parametrize("kind", ["baseline", "reset"])
@pytest.mark.parametrize("after", [False, True])
def test_put_failure_preserves_all_errors_and_exact_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, after: bool
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    original = data.store.put
    error = ExceptionGroup(
        "primary and cleanup", [OSError("write failed"), OSError("close failed")]
    )
    retained: list[EvidenceRef] = []

    def fail(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        if after:
            retained.append(original(raw, metadata))
        raise error

    before = set((tmp_path / "blobs").iterdir())
    with monkeypatch.context() as scoped:
        scoped.setattr(data.store, "put", fail)
        with pytest.raises(ExceptionGroup) as caught:
            data.publish(candidate, candidate.operation)
    assert caught.value is error
    assert len(set((tmp_path / "blobs").iterdir()) - before) == int(after)
    ref = data.publish(candidate, candidate.operation)
    if retained:
        assert ref == retained[0]
    assert data.load(kind, ref, command()) == candidate


@pytest.mark.parametrize("kind", ["baseline", "reset"])
def test_post_commit_cancel_retains_reference_for_cleanup_read(
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
    original = data.store.put

    def cancel(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        result = original(raw, metadata)
        data.switch.cancelled = True
        return result

    with monkeypatch.context() as scoped:
        scoped.setattr(data.store, "put", cancel)
        with pytest.raises(StateCommitUnconfirmed) as caught:
            data.publish(candidate, operation)
    assert isinstance(caught.value.__cause__, OperationStopped)
    cleanup = command(attempt="attempt", cleanup_parent=operation.operation_id)
    assert data.load(kind, caught.value.reference, cleanup) == candidate


@pytest.mark.parametrize("kind", ["baseline", "reset"])
@pytest.mark.parametrize("bad", [None, {}, [], True])
def test_bad_input_rejected_before_storage(
    tmp_path: Path, kind: str, bad: object
) -> None:
    data = fixture(tmp_path)
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(ValidationError):
        if kind == "baseline":
            data.adapter.publish_baseline(cast(BaselineReceipt, bad), command())
        else:
            data.adapter.publish_reset(cast(ResetReceipt, bad), command())
    assert set((tmp_path / "blobs").iterdir()) == before


@pytest.mark.parametrize("kind", ["baseline", "reset"])
@pytest.mark.parametrize("field", ["run_id", "owner_id", "attempt_id"])
def test_wrong_read_scope_rejected_before_authority(
    tmp_path: Path, kind: str, field: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    ref = data.publish(candidate, candidate.operation)
    before = list(data.authority.calls)
    with pytest.raises(OwnershipConflict):
        data.load(kind, ref, command().model_copy(update={field: "other"}))
    assert data.authority.calls == before


@pytest.mark.parametrize("kind", ["baseline", "reset"])
@pytest.mark.parametrize("field", ["visibility", "content_schema"])
def test_load_requires_exact_private_summary_reference(
    tmp_path: Path, kind: str, field: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    ref = data.publish(candidate, candidate.operation)
    changed = ref.model_copy(
        update={field: "public" if field == "visibility" else "old-summary/1"}
    )
    with pytest.raises(ValueError):
        data.load(kind, changed, command())


@pytest.mark.parametrize("kind", ["baseline", "reset"])
def test_expiry_during_semantic_verification_prevents_write(
    tmp_path: Path, kind: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    clock = ManualClock()
    clock.wall = candidate.operation.deadline - timedelta(seconds=1)
    data.adapter.controls = OperationGuards(clock, data.switch)

    class SlowAuthority(UnitStateAuthority):
        def verify_baseline(
            self, inputs: BaselineInputs, receipt: BaselineReceipt, op: OperationContext
        ) -> None:
            super().verify_baseline(inputs, receipt, op)
            clock.sleep(2)

        def verify_reset(
            self, inputs: ResetInputs, receipt: ResetReceipt, op: OperationContext
        ) -> None:
            super().verify_reset(inputs, receipt, op)
            clock.sleep(2)

    authority = SlowAuthority()
    data.adapter.authority = authority
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(OperationStopped):
        data.publish(candidate, candidate.operation)
    assert authority.calls == [kind]
    assert set((tmp_path / "blobs").iterdir()) == before
