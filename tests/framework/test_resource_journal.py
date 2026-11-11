"""Real file-journal transactions and recoverability after partial initialization."""

import hashlib
import fcntl
import multiprocessing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.resource_journal import FileResourceJournal
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    InvalidTransition,
    OperationStopped,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    CancellationRef,
    CleanupFailure,
    ClosureReceipt,
    OperationContext,
    RecoveryPlan,
    ResourceOwner,
    ResourceState,
)
from lab_generate_skill.runtime.lifecycle import OperationGuards


class NoCancellation:
    def is_cancelled(self, reference: CancellationRef) -> bool:
        return False


def context(token: AllocationToken, name: str = "register") -> OperationContext:
    return OperationContext(
        operation_id=name,
        run_id=token.owner.run_id,
        owner_id=token.owner.owner_id,
        attempt_id=token.attempt_id,
        allocation_id=token.allocation_id,
        recovery_ref=token.recovery_ref,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
    )


def prepare(root: Path) -> tuple[FileResourceJournal, AllocationToken, EvidenceRef]:
    store = FileEvidenceStore(root)
    owner = ResourceOwner(
        run_id="run", owner_id="owner", job_id="job", worker_id="worker"
    )
    baseline = store.put(
        b"baseline",
        EvidenceMetadata(
            media_type="text/plain",
            content_schema="baseline/1",
            visibility="private",
            producer="site",
        ),
    )
    plan = RecoveryPlan(
        recovery_id="recover",
        owner=owner,
        attempt_id="attempt",
        baseline_ref=baseline,
        restore_component_id="site.restore",
        restore_component_version="1",
        state_coverage=("database", "mail", "files"),
    )
    ref = store.put(
        plan.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="recovery-plan/1",
            visibility="private",
            producer="controller",
        ),
    )
    token = AllocationToken(
        allocation_id="allocation",
        owner=owner,
        scope="attempt",
        attempt_id="attempt",
        resource_kind="site",
        expected_resource_id="private-instance",
        provider_id="site.provider",
        provider_version="1",
        recovery_ref=ref,
    )
    journal = FileResourceJournal(
        root, owner, OperationGuards(SystemClock(), NoCancellation()), store
    )
    return journal, token, baseline


def begin(
    journal: FileResourceJournal, token: AllocationToken, proof: EvidenceRef
) -> None:
    from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent

    op = context(token, "begin-acquire")
    intent = ResourceAcquisitionIntent(
        token=token, operation=op, configuration_ref=proof
    )
    ref = FileEvidenceStore(journal._root).put(
        intent.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="resource-acquisition-intent/1",
            visibility="private",
            producer="test",
        ),
    )
    journal.begin_acquire(token, ref, 0, op)


def cleanup(token: AllocationToken, name: str) -> OperationContext:
    return context(token).cleanup(name, now=datetime.now(timezone.utc), seconds=30)


def test_registration_precedes_partial_side_effect_and_survives_new_process_object(
    tmp_path: Path,
) -> None:
    journal, token, proof = prepare(tmp_path)
    registered = journal.register(token, context(token))
    assert registered.state == "registered"
    begin(journal, token, proof)
    registered = journal.read(token, context(token, "before-effect"))

    def failed_prepare() -> None:
        (tmp_path / "partial-resource").write_text("created before prepare returned")
        raise RuntimeError("prepare failed before returning a lease")

    with pytest.raises(RuntimeError):
        failed_prepare()
    restarted = FileResourceJournal(
        tmp_path,
        token.owner,
        OperationGuards(SystemClock(), NoCancellation()),
        FileEvidenceStore(tmp_path),
    )
    records = restarted.records(token.owner, cleanup(token, "discover"))
    assert records == (registered,)
    closing = restarted.advance(
        token, "closing", (proof,), registered.revision, cleanup(token, "close-start")
    )
    (tmp_path / "partial-resource").unlink()
    closed = restarted.advance(
        token, "closed", (proof,), closing.revision, cleanup(token, "close-done")
    )
    assert closed.state == "closed"
    assert closed.token.owner == token.owner
    assert closed.events[0] == registered.events[0]
    with pytest.raises(InvalidTransition):
        restarted.advance(
            token, "acquired", (proof,), closed.revision, context(token, "reopen")
        )


def test_operation_replay_is_idempotent_but_changed_evidence_rejected(
    tmp_path: Path,
) -> None:
    journal, token, proof = prepare(tmp_path)
    journal.register(token, context(token))
    begin(journal, token, proof)
    op = context(token, "acquire")
    acquired = journal.advance(token, "acquired", (proof,), 1, op)
    assert journal.advance(token, "acquired", (proof,), 1, op) == acquired
    with pytest.raises(OwnershipConflict):
        journal.advance(token, "acquired", (), 1, op)
    with pytest.raises(RevisionConflict):
        journal.advance(token, "closing", (proof,), 0, cleanup(token, "close"))


def test_other_owner_cannot_replace_existing_allocation(tmp_path: Path) -> None:
    journal, token, _ = prepare(tmp_path)
    journal.register(token, context(token))
    changed = token.model_dump()
    changed["expected_resource_id"] = "replacement"
    replacement = AllocationToken.model_validate(changed)
    with pytest.raises(OwnershipConflict):
        journal.register(replacement, context(replacement, "different-plan"))
    with pytest.raises(OwnershipConflict):
        journal.records(
            ResourceOwner(
                run_id="run", owner_id="other", job_id="new", worker_id="new"
            ),
            cleanup(token, "inspect"),
        )


def test_recovery_plan_must_actually_be_persisted(tmp_path: Path) -> None:
    journal, token, _ = prepare(tmp_path)
    (tmp_path / "blobs" / token.recovery_ref.sha256).unlink()
    with pytest.raises(EvidenceNotFound):
        journal.register(token, context(token))
    assert not list(tmp_path.glob("*.json"))


def test_write_failure_preserves_prior_record_and_cleans_temporary_file(
    tmp_path: Path,
) -> None:
    journal, token, proof = prepare(tmp_path)
    journal.register(token, context(token))
    begin(journal, token, proof)
    prior = journal.read(token, context(token, "before-update"))
    with patch(
        "lab_generate_skill.adapters.ledger.resource_journal.os.replace",
        side_effect=OSError("injected publish failure"),
    ):
        with pytest.raises(OSError):
            journal.advance(token, "acquired", (proof,), 1, context(token, "acquire"))
    assert journal.read(token, context(token, "inspect")) == prior
    assert not list(tmp_path.glob(".pending-*"))


def test_lost_ack_after_commit_is_reconciled_without_another_event(
    tmp_path: Path,
) -> None:
    journal, token, proof = prepare(tmp_path)
    journal.register(token, context(token))
    begin(journal, token, proof)
    op = context(token, "acquire")
    # First fsync persists temporary bytes; second is after atomic replacement.
    with patch(
        "lab_generate_skill.adapters.ledger.resource_journal.os.fsync",
        side_effect=[None, OSError("lost commit acknowledgement")],
    ):
        with pytest.raises(OSError):
            journal.advance(token, "acquired", (proof,), 1, op)
    record = journal.advance(token, "acquired", (proof,), 1, op)
    assert record.revision == 2


def test_corrupt_and_symlink_records_are_not_trusted(tmp_path: Path) -> None:
    journal, token, _ = prepare(tmp_path)
    journal.register(token, context(token))
    path = tmp_path / (
        hashlib.sha256(token.allocation_id.encode()).hexdigest() + ".resource.json"
    )
    path.write_text("{invalid")
    with pytest.raises(EvidenceIntegrityError):
        journal.read(token, context(token, "read-bad"))
    path.unlink()
    other = tmp_path / "outside"
    other.write_text("{}")
    path.symlink_to(other)
    with pytest.raises(EvidenceIntegrityError):
        journal.read(token, context(token, "read-link"))


def test_expired_registration_has_no_side_effect(tmp_path: Path) -> None:
    journal, token, _ = prepare(tmp_path)
    data = context(token).model_dump()
    data["deadline"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(OperationStopped):
        journal.register(token, OperationContext.model_validate(data))
    assert not list(tmp_path.glob("*.lock"))


def test_lock_contention_obeys_deadline_without_modifying_record(
    tmp_path: Path,
) -> None:
    journal, token, proof = prepare(tmp_path)
    prior = journal.register(token, context(token))
    lock_path = tmp_path / (
        hashlib.sha256(token.allocation_id.encode()).hexdigest() + ".resource.json.lock"
    )
    with lock_path.open("rb") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
        data = context(token, "blocked-acquire").model_dump()
        data["deadline"] = datetime.now(timezone.utc) + timedelta(seconds=0.15)
        with pytest.raises(OperationStopped) as stopped:
            journal.advance(
                token, "acquired", (proof,), 0, OperationContext.model_validate(data)
            )
        assert stopped.value.reason_code == "DEADLINE_EXCEEDED"
    assert journal.read(token, context(token, "inspect")).revision == prior.revision


def test_primary_and_cleanup_errors_both_survive(tmp_path: Path) -> None:
    journal, token, proof = prepare(tmp_path)
    journal.register(token, context(token))
    begin(journal, token, proof)
    prior = journal.read(token, context(token, "before-update"))
    with (
        patch(
            "lab_generate_skill.adapters.ledger.resource_journal.os.replace",
            side_effect=OSError("publish failure"),
        ),
        patch(
            "lab_generate_skill.adapters.ledger.resource_journal.os.unlink",
            side_effect=PermissionError("cleanup failure"),
        ),
    ):
        with pytest.raises(ExceptionGroup) as group:
            journal.advance(token, "acquired", (proof,), 1, context(token, "acquire"))
    assert len(group.value.exceptions) == 2
    assert str(group.value.exceptions[0]) == "publish failure"
    assert str(group.value.exceptions[1]) == "cleanup failure"
    assert journal.read(token, context(token, "inspect")) == prior


def test_cleanup_failure_retains_primary_error_and_cannot_claim_closed(
    tmp_path: Path,
) -> None:
    from pydantic import ValidationError

    journal, token, proof = prepare(tmp_path)
    journal.register(token, context(token))
    original = CleanupFailure(
        component_id="prepare", reason_code="INITIALIZATION_FAILED"
    )
    cleanup_error = CleanupFailure(component_id="reset", reason_code="RESET_FAILED")
    receipt = ClosureReceipt(
        token=token,
        operation_id="cleanup",
        status="failed",
        evidence=(proof,),
        primary_error=original,
        cleanup_errors=(cleanup_error,),
    )
    assert receipt.primary_error == original
    assert receipt.cleanup_errors == (cleanup_error,)
    with pytest.raises(ValidationError):
        ClosureReceipt.model_validate({**receipt.model_dump(), "status": "closed"})
    quarantined = journal.advance(
        token, "quarantined", (proof,), 0, cleanup(token, "quarantine")
    )
    with pytest.raises(InvalidTransition):
        journal.advance(
            token, "acquired", (proof,), quarantined.revision, context(token, "reuse")
        )


def _race(root: str, token_json: str, proof_json: str, index: int, marker: str) -> None:
    token = AllocationToken.model_validate_json(token_json)
    proof = EvidenceRef.model_validate_json(proof_json)
    journal = FileResourceJournal(
        Path(root),
        token.owner,
        OperationGuards(SystemClock(), NoCancellation()),
        FileEvidenceStore(Path(root)),
    )
    try:
        journal.advance(token, "acquired", (proof,), 1, context(token, f"race-{index}"))
        outcome = "committed"
    except RevisionConflict:
        outcome = "stale"
    Path(marker).write_text(outcome)


def test_independent_processes_cannot_both_advance_same_revision(
    tmp_path: Path,
) -> None:
    journal, token, proof = prepare(tmp_path)
    journal.register(token, context(token))
    begin(journal, token, proof)
    pool = multiprocessing.get_context("spawn")
    processes = [
        pool.Process(
            target=_race,
            args=(
                str(tmp_path),
                token.model_dump_json(),
                proof.model_dump_json(),
                index,
                str(tmp_path / f"race-{index}.txt"),
            ),
        )
        for index in range(4)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        if process.is_alive():
            process.terminate()
            process.join(5)
            pytest.fail("Concurrent journal test exceeded deadline")
        assert process.exitcode == 0
    outcomes = [(tmp_path / f"race-{index}.txt").read_text() for index in range(4)]
    assert outcomes.count("committed") == 1
    assert outcomes.count("stale") == 3
    assert journal.read(token, context(token, "inspect")).revision == 2


@pytest.mark.parametrize("revision", [None, True, False, "0", 0.0, -1, [], {}])
def test_invalid_revision_cannot_change_history(
    tmp_path: Path, revision: object
) -> None:
    journal, token, proof = prepare(tmp_path)
    prior = journal.register(token, context(token))
    with pytest.raises(ValueError):
        journal.advance(
            token, "acquired", (proof,), cast(int, revision), context(token, "acquire")
        )
    assert journal.read(token, context(token, "inspect")) == prior
    assert not list(tmp_path.glob(".pending-*"))


@pytest.mark.parametrize("evidence", [(), None, [], "", ({},)])
def test_invalid_or_absent_transition_evidence_preserves_record(
    tmp_path: Path, evidence: object
) -> None:
    journal, token, proof = prepare(tmp_path)
    journal.register(token, context(token))
    begin(journal, token, proof)
    prior = journal.read(token, context(token, "before-update"))
    with pytest.raises(ValidationError):
        journal.advance(
            token,
            "acquired",
            cast(tuple[EvidenceRef, ...], evidence),
            1,
            context(token, "acquire"),
        )
    assert journal.read(token, context(token, "inspect")) == prior


@pytest.mark.parametrize(
    ("state", "mode"),
    [("acquired", "cleanup"), ("closing", "execute"), ("quarantined", "execute")],
)
def test_operation_mode_cannot_gain_resource_privileges(
    tmp_path: Path, state: ResourceState, mode: str
) -> None:
    journal, token, proof = prepare(tmp_path)
    prior = journal.register(token, context(token))
    op = (
        cleanup(token, "wrong-mode")
        if mode == "cleanup"
        else context(token, "wrong-mode")
    )
    with pytest.raises(OwnershipConflict):
        journal.advance(token, state, (proof,), 0, op)
    assert journal.read(token, context(token, "inspect")) == prior


def test_repeated_registration_does_not_rewrite_or_reset_acquired_state(
    tmp_path: Path,
) -> None:
    journal, token, proof = prepare(tmp_path)
    op = context(token)
    first = journal.register(token, op)
    assert journal.register(token, op) == first
    begin(journal, token, proof)
    acquired = journal.advance(
        token, "acquired", (proof,), 1, context(token, "acquire")
    )
    assert journal.register(token, op) == acquired
    assert journal.records(token.owner, context(token, "inspect")) == (acquired,)


def test_unregistered_resource_read_and_advance_do_not_create_a_record(
    tmp_path: Path,
) -> None:
    journal, token, proof = prepare(tmp_path)
    assert journal.records(token.owner, context(token, "empty")) == ()
    with pytest.raises(EvidenceIntegrityError):
        journal.read(token, context(token, "read"))
    with pytest.raises(EvidenceIntegrityError):
        journal.advance(token, "acquired", (proof,), 0, context(token, "acquire"))
    assert not list(tmp_path.glob("*.json"))
