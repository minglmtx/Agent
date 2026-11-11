"""Run-level read contract: actual original record, full binding, no writes."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.claims import SourceClaimRecord, check_source_claim
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.domain.task import TaskBinding
from claim_fixtures import fixture, operation


def test_source_read_and_repeat_keep_original_registration(tmp_path: Path) -> None:
    f = fixture(tmp_path)
    receipt = f.ledger().claim(f.binding, operation(f.binding))
    before = f.path.read_bytes()
    blobs = set((tmp_path / "evidence" / "blobs").iterdir())
    for _ in range(2):
        assert (
            f.ledger().require_source(
                receipt.reference, f.binding.run, f.binding.task, operation(f.binding)
            )
            == receipt.record
        )
    assert f.authority.read_calls == 2 and f.authority.create_calls == 1
    assert f.path.read_bytes() == before
    assert set((tmp_path / "evidence" / "blobs").iterdir()) == blobs


@pytest.mark.parametrize(
    "change", ["worker", "release", "alias", "private", "baseline"]
)
def test_complete_binding_not_only_task_identity(tmp_path: Path, change: str) -> None:
    f = fixture(tmp_path)
    receipt = f.ledger().claim(f.binding, operation(f.binding))
    run, task = f.binding.run.model_dump(), f.binding.task.model_dump()
    if change == "worker":
        run["owner"]["worker_id"] = "other"
    elif change == "release":
        run["release_ref"]["sha256"] = "f" * 64
    elif change == "alias":
        task["identity"]["task_id"] = "other"
    else:
        task["private_spec_ref" if change == "private" else "baseline_ref"][
            "sha256"
        ] = ("f" * 64)
    before = f.path.read_bytes()
    with pytest.raises(OwnershipConflict):
        f.ledger().require_source(
            receipt.reference,
            RunBinding.model_validate(run),
            TaskBinding.model_validate(task),
            operation(f.binding),
        )
    assert f.path.read_bytes() == before


@pytest.mark.parametrize(
    "fault",
    [
        "missing_record",
        "corrupt_record",
        "missing_cas",
        "wrong_cas",
        "denied",
        "expired",
        "attempt",
    ],
)
def test_source_consumer_failures_do_not_reclaim(tmp_path: Path, fault: str) -> None:
    f = fixture(tmp_path)
    receipt = f.ledger().claim(f.binding, operation(f.binding))
    reference = receipt.reference
    op = operation(f.binding)
    expected: type[Exception]
    if fault == "missing_record":
        f.path.unlink()
        expected = EvidenceIntegrityError
    elif fault == "corrupt_record":
        f.path.write_bytes(b"{}")
        expected = EvidenceIntegrityError
    elif fault == "missing_cas":
        (tmp_path / "evidence" / "blobs" / reference.sha256).unlink()
        expected = EvidenceNotFound
    elif fault == "wrong_cas":
        changed = receipt.record.model_copy(update={"operation": operation(f.binding)})
        reference = f.store.put(
            changed.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="source-claim/1",
                visibility="private",
                producer="unit",
            ),
        )
        expected = EvidenceIntegrityError
    elif fault == "denied":
        f.authority.denied = True
        expected = OwnershipConflict
    elif fault == "expired":
        op = op.model_copy(
            update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
        expected = OperationStopped
    else:
        op = operation(f.binding, attempt="attempt")
        expected = OwnershipConflict
    before = f.path.read_bytes() if f.path.exists() else None
    with pytest.raises(expected):
        f.ledger().require_source(reference, f.binding.run, f.binding.task, op)
    assert (f.path.read_bytes() if f.path.exists() else None) == before
    assert f.authority.create_calls == 1


@pytest.mark.parametrize("value", [None, {}, [], "", True, 1])
def test_invalid_source_parameters_fail_without_ownership_changes(
    tmp_path: Path, value: object
) -> None:
    f = fixture(tmp_path)
    receipt = f.ledger().claim(f.binding, operation(f.binding))
    before = f.path.read_bytes()
    with pytest.raises(ValidationError):
        f.ledger().require_source(
            cast(EvidenceRef, value),
            f.binding.run,
            f.binding.task,
            operation(f.binding),
        )
    with pytest.raises(ValidationError):
        check_source_claim(
            cast(SourceClaimRecord, value),
            receipt.reference,
            f.binding.run,
            f.binding.task,
        )
    assert f.path.read_bytes() == before


def test_consumer_revalidates_port_record_and_canonical_reference(
    tmp_path: Path,
) -> None:
    f = fixture(tmp_path)
    receipt = f.ledger().claim(f.binding, operation(f.binding))
    for changed in (
        receipt.reference.model_copy(update={"sha256": "f" * 64}),
        receipt.reference.model_copy(
            update={"size_bytes": receipt.reference.size_bytes + 1}
        ),
        receipt.reference.model_copy(update={"visibility": "public"}),
    ):
        with pytest.raises(ValueError):
            check_source_claim(receipt.record, changed, f.binding.run, f.binding.task)


@pytest.mark.parametrize("when", ["before_read", "during_authority"])
def test_cancelled_source_read_never_returns_permission(
    tmp_path: Path, when: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = fixture(tmp_path)
    receipt = f.ledger().claim(f.binding, operation(f.binding))
    op = operation(f.binding)
    op = op.model_copy(
        update={
            "cancellation_ref": CancellationRef(
                channel_id="cancel",
                run_id=op.run_id,
                owner_id=op.owner_id,
            )
        }
    )
    if when == "before_read":
        f.cancel.cancelled = True
    else:

        def cancel(*args: object) -> None:
            f.cancel.cancelled = True

        monkeypatch.setattr(f.authority, "verify_owner", cancel)
    before = f.path.read_bytes()
    with pytest.raises(OperationStopped):
        f.ledger().require_source(receipt.reference, f.binding.run, f.binding.task, op)
    assert f.path.read_bytes() == before
