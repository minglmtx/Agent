"""Validation storage changes cannot overwrite or impersonate original claims."""

import json
from pathlib import Path
from typing import cast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import pytest
from lab_generate_skill.adapters.ledger.source_stage_validation import (
    FileSourceStageValidations,
)
from lab_generate_skill.domain.claims import ClaimCommitUnconfirmed, SourceClaimBinding
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.execution import AttemptBinding
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.ports.source_stage_validation import (
    SourceStageValidationAuthority,
)
from claim_fixtures import operation
from stage_validation_fixtures import stage_fixture, UnitStageAuthority
from test_model_sender_faults import FaultStore


def test_explicit_validation_preserves_canonical_parent_and_replay_identity(
    tmp_path: Path,
) -> None:
    s = stage_fixture(tmp_path)
    original = s.original.path.read_bytes()
    op = operation(s.binding)
    claim = s.ledger().claim(s.binding, op)
    assert s.path.read_bytes() == claim.record.model_dump_json().encode()
    assert s.original.path.read_bytes() == original
    assert s.ledger().claim(s.binding, operation(s.binding)) == claim
    assert s.authority.create_calls == 1
    assert s.authority.parent_calls == 2 and s.authority.current_calls == 1
    assert (
        s.original.ledger().read(s.binding.key, operation(s.original.binding))
        == s.parent.record
    )
    with pytest.raises(OwnershipConflict):
        s.original.ledger().claim(s.binding, operation(s.binding))
    assert s.original.path.read_bytes() == original


@pytest.mark.parametrize(
    "change", ["authorization", "run", "job", "submission", "release-metadata"]
)
def test_slot_cannot_be_minted_by_changing_authorization_or_owner_ids(
    tmp_path: Path, change: str
) -> None:
    s = stage_fixture(tmp_path)
    first = s.ledger().claim(s.binding, operation(s.binding))
    if change in ("authorization", "release-metadata"):
        field = (
            "authorization_ref" if change == "authorization" else "target_release_ref"
        )
        value = s.validation.model_dump(mode="json")
        value[field]["producer"] = "different-description"
        changed = SourceStageValidation.model_validate_json(json.dumps(value))
        assert changed.filename == s.validation.filename
    else:
        value = s.binding.model_dump(mode="json")
        if change == "submission":
            value["run"]["submission_key"] = "other"
        else:
            value["run"]["owner"][change + "_id"] = "other"
        changed_binding = SourceClaimBinding.model_validate(value)
        with pytest.raises(OwnershipConflict):
            s.ledger().claim(changed_binding, operation(changed_binding))
    assert s.path.read_bytes() == first.record.model_dump_json().encode()


@pytest.mark.parametrize(
    "change", ["scope", "alias", "private-task", "old-run", "old-job", "release"]
)
def test_validation_requires_exact_original_task_and_fresh_binding(
    tmp_path: Path, change: str
) -> None:
    s = stage_fixture(tmp_path)
    value = s.binding.model_dump(mode="json")
    if change == "scope":
        value["scope_id"] = "other"
    elif change == "alias":
        value["task"]["identity"]["task_id"] = "other"
    elif change == "private-task":
        value["task"]["registration_id"] = "other"
    elif change in ("old-run", "old-job"):
        field = "run_id" if change == "old-run" else "job_id"
        value["run"]["owner"][field] = s.original.binding.model_dump(mode="json")[
            "run"
        ]["owner"][field]
    else:
        value["run"]["release_ref"] = s.original.binding.run.release_ref.model_dump(
            mode="json"
        )
    binding = SourceClaimBinding.model_validate(value)
    with pytest.raises(OwnershipConflict):
        s.validation.require_current_binding(binding)
    assert not s.path.exists()


@pytest.mark.parametrize(
    "change",
    ["unchanged-release", "public-authorization", "wrong-authorization-schema"],
)
def test_validation_descriptor_rejects_invalid_basis(
    tmp_path: Path, change: str
) -> None:
    s = stage_fixture(tmp_path)
    value = s.validation.model_dump(mode="json")
    if change == "unchanged-release":
        value["target_release_ref"] = s.original.binding.run.release_ref.model_dump(
            mode="json"
        )
    elif change == "public-authorization":
        value["authorization_ref"]["visibility"] = "public"
    else:
        value["authorization_ref"]["content_schema"] = "fixture/1"
    expected = (
        "changed release"
        if change == "unchanged-release"
        else "Expected private task-stage-validation-authorization/1"
    )
    with pytest.raises(ValueError, match=expected):
        SourceStageValidation.model_validate_json(json.dumps(value))


@pytest.mark.parametrize("which", ["parent", "current"])
@pytest.mark.parametrize(
    "consumer",
    ["read", "source", "source-body", "attempt", "attempt-body", "reconcile"],
)
def test_revocation_is_checked_on_every_claim_consumer(
    tmp_path: Path, which: str, consumer: str
) -> None:
    s = stage_fixture(tmp_path)
    creation = operation(s.binding)
    receipt = s.ledger().claim(s.binding, creation)
    before = s.path.read_bytes(), s.original.path.read_bytes()
    s.authority.denied = which
    op = operation(s.binding)
    attempt = AttemptBinding(
        run=s.binding.run,
        task=s.binding.task.identity,
        attempt_id="stage-attempt",
        claim_ref=receipt.reference,
    )
    with pytest.raises(OwnershipConflict):
        if consumer == "read":
            s.ledger().read(s.binding.key, op)
        elif consumer == "source":
            s.ledger().require_source(
                receipt.reference, s.binding.run, s.binding.task, op
            )
        elif consumer == "source-body":
            s.ledger().require_source_verified(
                receipt, s.binding.run, s.binding.task, op
            )
        elif consumer == "attempt":
            s.ledger().require(
                receipt.reference,
                attempt,
                op.model_copy(update={"attempt_id": attempt.attempt_id}),
            )
        elif consumer == "attempt-body":
            s.ledger().require_verified(
                receipt,
                attempt,
                op.model_copy(update={"attempt_id": attempt.attempt_id}),
            )
        else:
            s.ledger().reconcile(
                s.binding.key,
                op.model_copy(
                    update={
                        "mode": "cleanup",
                        "parent_operation_id": creation.operation_id,
                    }
                ),
            )
    assert (s.path.read_bytes(), s.original.path.read_bytes()) == before


@pytest.mark.parametrize("change", ["missing", "corrupt", "missing-lock"])
def test_parent_integrity_is_mandatory_before_child_commit(
    tmp_path: Path, change: str
) -> None:
    s = stage_fixture(tmp_path)
    if change == "missing":
        s.original.path.unlink()
    elif change == "corrupt":
        s.original.path.write_bytes(b"{}")
    else:
        s.original.path.with_name(s.original.path.name + ".lock").unlink()
    with pytest.raises(EvidenceIntegrityError):
        s.ledger().claim(s.binding, operation(s.binding))
    assert not s.path.exists() and s.authority.create_calls == 0


@pytest.mark.parametrize("after", [False, True])
def test_lost_receipt_keeps_same_validation_and_original_parent(
    tmp_path: Path, after: bool
) -> None:
    s = stage_fixture(tmp_path)
    parent = s.original.path.read_bytes()
    store = FaultStore(s.original.store, "source-claim/1", after)
    creation = operation(s.binding)
    with pytest.raises(ClaimCommitUnconfirmed) as error:
        s.ledger(store).claim(s.binding, creation)
    assert s.path.read_bytes() == error.value.record.model_dump_json().encode()
    assert s.original.path.read_bytes() == parent
    recovered = s.ledger().reconcile(
        s.binding.key,
        operation(s.binding).model_copy(
            update={"mode": "cleanup", "parent_operation_id": creation.operation_id}
        ),
    )
    assert recovered.record == error.value.record
    assert s.authority.create_calls == 1
    if store.written is not None:
        assert recovered.reference == store.written


def test_missing_live_authority_cannot_create_a_validation(tmp_path: Path) -> None:
    s = stage_fixture(tmp_path)
    with pytest.raises(TypeError):
        FileSourceStageValidations(
            s.original.root / "claims",
            s.binding.scope_id,
            s.original.controls,
            s.original.store,
            s.original.plans,
            cast(SourceStageValidationAuthority, object()),
            validation=s.validation,
        )
    assert not s.path.exists()


@pytest.mark.parametrize("mode", ["cancelled", "expired"])
def test_stopped_validation_does_not_commit_or_rewrite_parent(
    tmp_path: Path, mode: str
) -> None:
    s = stage_fixture(tmp_path)
    parent = s.original.path.read_bytes()
    op = operation(s.binding)
    if mode == "cancelled":
        s.original.cancel.cancelled = True
        op = op.model_copy(
            update={
                "cancellation_ref": CancellationRef(
                    channel_id="unit-stage-cancel",
                    run_id=op.run_id,
                    owner_id=op.owner_id,
                )
            }
        )
    else:
        op = op.model_copy(
            update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
    with pytest.raises(OperationStopped):
        s.ledger().claim(s.binding, op)
    assert not s.path.exists() and s.original.path.read_bytes() == parent


def test_competing_validated_bindings_have_only_one_durable_winner(
    tmp_path: Path,
) -> None:
    s = stage_fixture(tmp_path)
    parent = s.original.path.read_bytes()
    other = SourceClaimBinding.model_validate(
        s.binding.model_copy(
            update={
                "run": s.binding.run.model_copy(
                    update={
                        "owner": s.binding.run.owner.model_copy(
                            update={"owner_id": "competing-unit-owner"}
                        )
                    }
                )
            }
        )
    )

    def create(binding: SourceClaimBinding) -> str:
        f = s.original
        ledger = FileSourceStageValidations(
            f.root / "claims",
            binding.scope_id,
            f.controls,
            f.store,
            f.plans,
            UnitStageAuthority(s.validation, binding),
            validation=s.validation,
        )
        try:
            ledger.claim(binding, operation(binding))
            return "committed"
        except OwnershipConflict:
            return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create, (s.binding, other)))
    assert sorted(outcomes) == ["committed", "refused"]
    assert s.original.path.read_bytes() == parent
    assert len(list(s.path.parent.glob("*.stage-validation-claim.json"))) == 1
