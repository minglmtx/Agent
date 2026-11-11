"""Source claim input/state contracts and actual plan/attempt consumption."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.claims import (
    SourceClaimBinding,
    SourceClaimKey,
    SourceClaimReceipt,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import CancellationRef
from claim_fixtures import fixture, operation


def test_exact_replay_preserves_original_registration_and_attempt_consumes_real_claim(
    tmp_path: Path,
) -> None:
    f = fixture(tmp_path)
    ledger = f.ledger()
    op = operation(f.binding)
    first = ledger.claim(f.binding, op)
    before = f.path.read_bytes()
    assert ledger.claim(f.binding, operation(f.binding)) == first
    assert f.authority.create_calls == 1 and f.authority.read_calls == 1
    assert ledger.read(f.binding.key, operation(f.binding)) == first.record
    assert (
        ledger.require(
            first.reference,
            f.attempt(first.reference),
            operation(f.binding, attempt="attempt"),
        )
        == first.record
    )
    assert f.path.read_bytes() == before and first.record.operation == op
    assert first.reference.visibility == "private"


@pytest.mark.parametrize(
    "change",
    [
        "run",
        "owner",
        "job",
        "worker",
        "release",
        "plan",
        "submission",
        "alias",
        "split",
        "family",
        "private_spec",
        "scope",
    ],
)
def test_same_source_cannot_bypass_ownership_by_changing_binding(
    tmp_path: Path, change: str
) -> None:
    f = fixture(tmp_path)
    first = f.ledger().claim(f.binding, operation(f.binding))
    before = f.path.read_bytes()
    value = f.binding.model_dump(mode="json")
    if change in ("run", "owner", "job", "worker"):
        value["run"]["owner"][change + "_id"] = "different"
    elif change in ("release", "plan"):
        value["run"][change + "_ref"]["sha256"] = "f" * 64
    elif change == "submission":
        value["run"]["submission_key"] = "different"
    elif change == "alias":
        value["task"]["identity"]["task_id"] = "different"
    elif change == "split":
        value["task"]["identity"]["split"] = "test"
    elif change == "family":
        value["task"]["identity"]["family"] = "different"
    elif change == "private_spec":
        value["task"]["private_spec_ref"]["sha256"] = "f" * 64
    else:
        value["scope_id"] = "different"
    changed = SourceClaimBinding.model_validate(value)
    assert changed.key.filename == f.binding.key.filename
    with pytest.raises(OwnershipConflict):
        f.ledger().claim(changed, operation(changed))
    assert f.path.read_bytes() == before
    assert f.ledger().read(f.binding.key, operation(f.binding)) == first.record


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        "",
        True,
        1,
        [],
        {"scope_id": "unit-scope", "source_task_id": "../escape"},
    ],
)
def test_bad_key_and_binding_types_fail_before_claim_side_effects(
    tmp_path: Path, value: object
) -> None:
    f = fixture(tmp_path)
    with pytest.raises(ValidationError):
        f.ledger().claim(cast(SourceClaimBinding, value), operation(f.binding))
    with pytest.raises(ValidationError):
        f.ledger().read(cast(SourceClaimKey, value), operation(f.binding))
    assert not list((tmp_path / "claims").iterdir())


@pytest.mark.parametrize("change", ["absent_source", "task_config", "missing_plan"])
def test_plan_membership_and_actual_evidence_required_before_creation(
    tmp_path: Path, change: str
) -> None:
    f = fixture(tmp_path)
    value = f.binding.model_dump(mode="json")
    if change == "absent_source":
        value["task"]["identity"]["source_task_id"] = "absent"
    elif change == "task_config":
        value["task"]["registration_id"] = "different"
    else:
        (f.root / "evidence" / "blobs" / f.binding.run.plan_ref.sha256).unlink()
    changed = SourceClaimBinding.model_validate(value)
    with pytest.raises((OwnershipConflict, EvidenceNotFound)):
        f.ledger().claim(changed, operation(changed))
    assert not (tmp_path / "claims" / changed.key.filename).exists()
    assert not (tmp_path / "claims" / (changed.key.filename + ".initialized")).exists()
    assert f.authority.create_calls == 0


def test_permission_denial_and_noncreating_operation_do_not_claim(
    tmp_path: Path,
) -> None:
    f = fixture(tmp_path)
    f.authority.denied = True
    with pytest.raises(OwnershipConflict):
        f.ledger().claim(f.binding, operation(f.binding))
    assert not f.path.exists()
    f.authority.denied = False
    op = operation(f.binding)
    cleanup = op.cleanup("clean", now=datetime.now(timezone.utc), seconds=10)
    for bad in (cleanup, operation(f.binding, attempt="attempt")):
        with pytest.raises(OwnershipConflict):
            f.ledger().claim(f.binding, bad)
    receipt = f.ledger().claim(f.binding, op)
    f.authority.denied = True
    with pytest.raises(OwnershipConflict):
        f.ledger().require(
            receipt.reference,
            f.attempt(receipt.reference),
            operation(f.binding, attempt="attempt"),
        )


@pytest.mark.parametrize("mode", ["cancel", "expired"])
def test_cancelled_or_expired_creation_has_no_files(tmp_path: Path, mode: str) -> None:
    f = fixture(tmp_path)
    op = operation(f.binding)
    if mode == "expired":
        op = op.model_copy(
            update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
    else:
        f.cancel.cancelled = True
        op = op.model_copy(
            update={
                "cancellation_ref": CancellationRef(
                    channel_id="cancel", run_id=op.run_id, owner_id=op.owner_id
                )
            }
        )
    with pytest.raises(OperationStopped):
        f.ledger().claim(f.binding, op)
    assert not list((tmp_path / "claims").iterdir())


@pytest.mark.parametrize(
    "change",
    ["attempt", "run", "task", "reference", "visibility", "cas_bytes", "forged_record"],
)
def test_require_checks_actual_claim_and_full_attempt(
    tmp_path: Path, change: str
) -> None:
    f = fixture(tmp_path)
    receipt = f.ledger().claim(f.binding, operation(f.binding))
    attempt = f.attempt(receipt.reference)
    ref = receipt.reference
    op = operation(f.binding, attempt="attempt")
    if change == "attempt":
        op = operation(f.binding, attempt="other")
    elif change == "run":
        attempt = attempt.model_copy(
            update={"run": attempt.run.model_copy(update={"submission_key": "other"})}
        )
    elif change == "task":
        attempt = attempt.model_copy(
            update={"task": attempt.task.model_copy(update={"family": "other"})}
        )
    elif change == "reference":
        ref = ref.model_copy(update={"sha256": "f" * 64})
    elif change == "visibility":
        ref = ref.model_copy(update={"visibility": "public"})
        attempt = attempt.model_copy(update={"claim_ref": ref})
    elif change == "cas_bytes":
        (f.root / "evidence" / "blobs" / ref.sha256).write_bytes(b"corrupt")
    else:
        record = receipt.record.model_copy(update={"operation": operation(f.binding)})
        ref = f.store.put(
            record.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="source-claim/1",
                visibility="private",
                producer="unit-forged",
            ),
        )
        attempt = attempt.model_copy(update={"claim_ref": ref})
    with pytest.raises((OwnershipConflict, EvidenceIntegrityError, ValueError)):
        f.ledger().require(ref, attempt, op)


@pytest.mark.parametrize(
    "change", ["snapshot_missing", "snapshot_corrupt", "marker_missing"]
)
def test_used_claim_never_reopens_when_snapshot_or_marker_missing(
    tmp_path: Path, change: str
) -> None:
    f = fixture(tmp_path)
    f.ledger().claim(f.binding, operation(f.binding))
    if change == "snapshot_missing":
        f.path.unlink()
    elif change == "snapshot_corrupt":
        f.path.write_bytes(b"broken")
    else:
        f.path.with_name(f.path.name + ".initialized").unlink()
    with pytest.raises(EvidenceIntegrityError):
        f.ledger().claim(f.binding, operation(f.binding))


def test_receipt_cannot_point_to_different_or_oversized_claim(tmp_path: Path) -> None:
    f = fixture(tmp_path)
    result = f.ledger().claim(f.binding, operation(f.binding))
    bad = result.reference.model_copy(update={"sha256": "f" * 64})
    with pytest.raises(ValueError):
        SourceClaimReceipt(record=result.record, reference=bad)
    big = result.reference.model_copy(update={"size_bytes": 128 * 1024 + 1})
    with pytest.raises(ValueError):
        f.ledger().require(big, f.attempt(big), operation(f.binding, attempt="attempt"))


def test_missing_claim_is_explicit_and_does_not_register(tmp_path: Path) -> None:
    f = fixture(tmp_path)
    with pytest.raises(EvidenceNotFound):
        f.ledger().read(f.binding.key, operation(f.binding))
    assert not f.path.exists()
