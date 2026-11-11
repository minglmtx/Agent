"""Claim publication/cleanup failures retain ownership before any receipt."""

from pathlib import Path
from unittest.mock import patch
import pytest
from lab_generate_skill.adapters.storage.atomic_snapshot import SnapshotTransaction
from lab_generate_skill.domain.claims import ClaimCommitUnconfirmed
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from claim_fixtures import fixture, operation
from test_model_sender_faults import FaultStore


@pytest.mark.parametrize("after", [False, True])
def test_cas_write_and_cleanup_failures_keep_original_claim(
    tmp_path: Path, after: bool
) -> None:
    f = fixture(tmp_path)
    store = FaultStore(f.store, "source-claim/1", after)
    with pytest.raises(ClaimCommitUnconfirmed) as error:
        f.ledger(store).claim(f.binding, operation(f.binding))
    assert error.value.reference is None
    cause = error.value.__cause__
    assert isinstance(cause, ExceptionGroup) and len(cause.exceptions) == 2
    assert (store.written is not None) == after
    original = f.ledger().read(f.binding.key, operation(f.binding))
    assert original == error.value.record
    changed = f.binding.model_copy(
        update={"run": f.binding.run.model_copy(update={"submission_key": "other"})}
    )
    with pytest.raises(OwnershipConflict):
        f.ledger().claim(changed, operation(changed))
    result = f.ledger().claim(f.binding, operation(f.binding))
    assert result.record == original
    if store.written is not None:
        assert result.reference == store.written


def test_snapshot_ack_loss_reads_back_original_operation(tmp_path: Path) -> None:
    f = fixture(tmp_path)
    write = SnapshotTransaction.write

    def lost(transaction: SnapshotTransaction, raw: bytes) -> None:
        write(transaction, raw)
        raise OSError("unit directory sync acknowledgement lost")

    with patch.object(SnapshotTransaction, "write", lost):
        with pytest.raises(ClaimCommitUnconfirmed) as error:
            f.ledger().claim(f.binding, operation(f.binding))
    assert error.value.reference is None and isinstance(error.value.__cause__, OSError)
    saved = f.path.read_bytes()
    result = f.ledger().claim(f.binding, operation(f.binding))
    assert result.record == error.value.record and f.path.read_bytes() == saved


def test_first_publish_failure_preserves_incomplete_initialization_fence(
    tmp_path: Path,
) -> None:
    f = fixture(tmp_path)
    with patch(
        "lab_generate_skill.adapters.storage.atomic_snapshot.os.replace",
        side_effect=OSError("unit replace failed"),
    ):
        with pytest.raises(ClaimCommitUnconfirmed) as error:
            f.ledger().claim(f.binding, operation(f.binding))
    assert isinstance(error.value.__cause__, OSError)
    assert (
        not f.path.exists() and f.path.with_name(f.path.name + ".initialized").exists()
    )
    with pytest.raises(EvidenceIntegrityError):
        f.ledger().claim(f.binding, operation(f.binding))


def test_replay_never_needs_the_old_plan_to_be_recreated(tmp_path: Path) -> None:
    f = fixture(tmp_path)
    original = f.ledger().claim(f.binding, operation(f.binding))
    (f.root / "evidence" / "blobs" / f.binding.run.plan_ref.sha256).unlink()
    assert f.ledger().claim(f.binding, operation(f.binding)) == original
    assert f.authority.create_calls == 1
    # This diagnostic replay is not execution admission; new sends still need
    # actual plan/claim authority and must not use this as a fallback.


def test_record_size_limit_rejects_before_opening_claim_directory(
    tmp_path: Path,
) -> None:
    f = fixture(tmp_path)
    task = f.binding.task.model_copy(
        update={
            "private_spec_ref": f.binding.task.private_spec_ref.model_copy(
                update={"content_schema": "x" * (128 * 1024)}
            )
        }
    )
    changed = f.binding.model_copy(update={"task": task})
    with pytest.raises(ValueError, match="size limit"):
        f.ledger().claim(changed, operation(changed))
    assert not list((tmp_path / "claims").iterdir())
