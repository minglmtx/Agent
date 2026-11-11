"""Expired registration can recover only its original receipt via cleanup."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import pytest
from lab_generate_skill.adapters.storage.atomic_snapshot import SnapshotTransaction
from lab_generate_skill.domain.claims import ClaimCommitUnconfirmed, SourceClaimKey
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.runtime.lifecycle import OperationGuards
from claim_fixtures import fixture, operation
from test_lifecycle import ManualClock
from test_model_sender_faults import FaultStore


def test_expired_registration_and_lost_cas_reconcile_without_plan_or_new_claim(
    tmp_path: Path,
) -> None:
    f = fixture(tmp_path)
    op = operation(f.binding)
    with pytest.raises(ClaimCommitUnconfirmed) as error:
        f.ledger(FaultStore(f.store, "source-claim/1", False)).claim(f.binding, op)
    original = error.value.record
    saved = f.path.read_bytes()
    clock = ManualClock()
    clock.wall = op.deadline + timedelta(seconds=1)
    f.controls = OperationGuards(clock, f.cancel)
    with pytest.raises(OperationStopped):
        f.ledger().claim(f.binding, op)
    (f.root / "evidence" / "blobs" / f.binding.run.plan_ref.sha256).unlink()
    cleanup = op.cleanup("cleanup", now=clock.wall, seconds=10)
    with patch.object(
        SnapshotTransaction,
        "write",
        side_effect=AssertionError("cleanup must not register"),
    ):
        first = f.ledger().reconcile(f.binding.key, cleanup)
        assert f.ledger().reconcile(f.binding.key, cleanup) == first
    assert first.record == original and f.path.read_bytes() == saved
    assert f.authority.create_calls == 1


@pytest.mark.parametrize(
    "change", ["execute", "parent", "owner", "run", "attempt", "allocation", "scope"]
)
def test_cleanup_cannot_change_original_identity_or_create_work(
    tmp_path: Path, change: str
) -> None:
    f = fixture(tmp_path)
    op = operation(f.binding)
    first = f.ledger().claim(f.binding, op)
    cleanup = op.cleanup("cleanup", now=datetime.now(timezone.utc), seconds=10)
    key = f.binding.key
    if change == "execute":
        cleanup = operation(f.binding)
    elif change == "scope":
        key = SourceClaimKey(scope_id="other", source_task_id=key.source_task_id)
    else:
        field = {
            "parent": "parent_operation_id",
            "owner": "owner_id",
            "run": "run_id",
            "attempt": "attempt_id",
            "allocation": "allocation_id",
        }[change]
        cleanup = cleanup.model_copy(update={field: "other"})
    saved = f.path.read_bytes()
    with pytest.raises(OwnershipConflict):
        f.ledger().reconcile(key, cleanup)
    assert f.path.read_bytes() == saved
    assert f.ledger().read(f.binding.key, operation(f.binding)) == first.record


def test_cleanup_missing_claim_does_not_initialize_it(tmp_path: Path) -> None:
    f = fixture(tmp_path)
    op = operation(f.binding)
    cleanup = op.cleanup("cleanup", now=datetime.now(timezone.utc), seconds=10)
    with pytest.raises(EvidenceNotFound):
        f.ledger().reconcile(f.binding.key, cleanup)
    assert (
        not f.path.exists()
        and not f.path.with_name(f.path.name + ".initialized").exists()
    )


@pytest.mark.parametrize("mode", ["expired", "cancel", "denied"])
def test_cleanup_respects_its_own_deadline_cancel_and_actual_authority(
    tmp_path: Path, mode: str
) -> None:
    f = fixture(tmp_path)
    op = operation(f.binding)
    f.ledger().claim(f.binding, op)
    cleanup = op.cleanup("cleanup", now=datetime.now(timezone.utc), seconds=10)
    if mode == "expired":
        cleanup = cleanup.model_copy(
            update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
    elif mode == "cancel":
        f.cancel.cancelled = True
        cleanup = cleanup.model_copy(
            update={
                "cancellation_ref": CancellationRef(
                    channel_id="cancel", run_id=op.run_id, owner_id=op.owner_id
                )
            }
        )
    else:
        f.authority.denied = True
    saved = f.path.read_bytes()
    with pytest.raises(OwnershipConflict if mode == "denied" else OperationStopped):
        f.ledger().reconcile(f.binding.key, cleanup)
    assert f.path.read_bytes() == saved


@pytest.mark.parametrize("after", [False, True])
def test_cleanup_cas_and_close_failure_retain_original_fact(
    tmp_path: Path, after: bool
) -> None:
    f = fixture(tmp_path)
    op = operation(f.binding)
    first = f.ledger().claim(f.binding, op)
    cleanup = op.cleanup("cleanup", now=datetime.now(timezone.utc), seconds=10)
    store = FaultStore(f.store, "source-claim/1", after)
    with pytest.raises(ClaimCommitUnconfirmed) as error:
        f.ledger(store).reconcile(f.binding.key, cleanup)
    assert error.value.record == first.record and isinstance(
        error.value.__cause__, ExceptionGroup
    )
    assert f.ledger().reconcile(f.binding.key, cleanup) == first
