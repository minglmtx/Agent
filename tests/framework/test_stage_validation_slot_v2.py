"""Parent-scoped v2 atomic slot tests; only isolated unit-authority claims."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from lab_generate_skill.domain.claims import ClaimCommitUnconfirmed, SourceClaimBinding
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from claim_fixtures import operation
from stage_validation_fixtures import StageFixture, UnitStageAuthority, stage_fixture
from construction_storage_fixtures import put
from test_model_sender_faults import FaultStore


def corrected_fixture(path: Path) -> StageFixture:
    s = stage_fixture(path)
    s.validation = SourceStageValidation.model_validate(
        s.validation.model_copy(update={"schema_version": "source-stage-validation/2"})
    )
    s.authority = UnitStageAuthority(s.validation, s.binding)
    return s


def competing(s: StageFixture) -> StageFixture:
    f = s.original
    target = s.validation.target_release_ref
    old = f.plans.load(s.binding.run, operation(s.binding))
    plan = RunPlan.model_validate(
        old.model_copy(update={"run_id": "competing-run", "release_ref": target})
    )
    run = s.binding.run.model_copy(
        update={
            "owner": s.binding.run.owner.model_copy(
                update={"run_id": "competing-run", "job_id": "competing-job"}
            ),
            "release_ref": target,
            "submission_key": "competing-submission",
        }
    )
    binding = SourceClaimBinding.model_validate(
        s.binding.model_copy(update={"run": run})
    )
    reference = f.plans.publish(plan, operation(binding))
    binding = SourceClaimBinding.model_validate(
        binding.model_copy(
            update={"run": run.model_copy(update={"plan_ref": reference})}
        )
    )
    validation = SourceStageValidation.model_validate(
        s.validation.model_copy(update={"target_release_ref": target})
    )
    return StageFixture(
        f, s.parent, binding, validation, UnitStageAuthority(validation, binding)
    )


def test_v2_replay_and_different_owner_race_have_one_winner(tmp_path: Path) -> None:
    s = corrected_fixture(tmp_path)
    other = competing(s)
    original = s.original.path.read_bytes()
    assert s.path == other.path

    def claim(case: StageFixture) -> str:
        try:
            case.ledger().claim(case.binding, operation(case.binding))
            return "claimed"
        except OwnershipConflict:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, (s, other)))
    assert sorted(results) == ["claimed", "rejected"]
    winner, loser = (s, other) if results[0] == "claimed" else (other, s)
    before = winner.path.read_bytes()
    assert (
        winner.ledger()
        .claim(winner.binding, operation(winner.binding))
        .record.model_dump_json()
        .encode()
        == before
    )
    with pytest.raises(OwnershipConflict):
        loser.ledger().claim(loser.binding, operation(loser.binding))
    assert s.original.path.read_bytes() == original
    assert winner.path.read_bytes() == before


def test_v2_lost_receipt_retains_slot_and_refuses_other_owner(tmp_path: Path) -> None:
    s = corrected_fixture(tmp_path)
    other = competing(s)
    with pytest.raises(ClaimCommitUnconfirmed):
        s.ledger(FaultStore(s.original.store, "source-claim/1", False)).claim(
            s.binding, operation(s.binding)
        )
    before = s.path.read_bytes()
    with pytest.raises(OwnershipConflict):
        other.ledger().claim(other.binding, operation(other.binding))
    assert s.path.read_bytes() == before
    assert (
        s.ledger()
        .claim(s.binding, operation(s.binding))
        .record.model_dump_json()
        .encode()
        == before
    )


@pytest.mark.parametrize("which", ["parent", "current"])
def test_v2_current_denial_does_not_erase_slot(tmp_path: Path, which: str) -> None:
    s = corrected_fixture(tmp_path)
    first = s.ledger().claim(s.binding, operation(s.binding))
    s.authority.denied = which
    with pytest.raises(OwnershipConflict):
        s.ledger().read(s.binding.key, operation(s.binding))
    assert s.path.read_bytes() == first.record.model_dump_json().encode()


def test_v2_missing_persisted_slot_cannot_initialize_empty_history(
    tmp_path: Path,
) -> None:
    s = corrected_fixture(tmp_path)
    s.ledger().claim(s.binding, operation(s.binding))
    s.path.unlink()
    with pytest.raises(EvidenceIntegrityError):
        s.ledger().claim(s.binding, operation(s.binding))
