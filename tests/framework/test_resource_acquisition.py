"""Once-only acquisition, namespace loss, competing starters and uncertain ack."""

import hashlib
import multiprocessing
import os
from pathlib import Path
from typing import cast
from unittest.mock import patch
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.resource_journal import FileResourceJournal
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    RevisionConflict,
    InvalidTransition,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import AllocationToken, OperationContext
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_resource_journal import prepare, context, cleanup, NoCancellation


def intent(
    root: Path, token: AllocationToken, proof: EvidenceRef, op: OperationContext
) -> EvidenceRef:
    value = ResourceAcquisitionIntent(
        token=token, operation=op, configuration_ref=proof
    )
    return FileEvidenceStore(root).put(
        value.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="resource-acquisition-intent/1",
            visibility="private",
            producer="test",
        ),
    )


def test_acquire_once_then_original_receipts_and_cleanup(tmp_path: Path) -> None:
    journal, token, proof = prepare(tmp_path)
    journal.register(token, context(token))
    op = context(token, "launch")
    ref = intent(tmp_path, token, proof, op)
    started = journal.begin_acquire(token, ref, 0, op)
    assert started.state == "acquiring" and started.events[-1].operation == op
    with pytest.raises(DispatchAlreadyCommitted):
        journal.begin_acquire(token, ref, 0, op)
    acquired_op = context(token, "acquired")
    acquired = journal.advance(token, "acquired", (proof,), 1, acquired_op)
    assert journal.advance(token, "acquired", (proof,), 1, acquired_op) == acquired
    with pytest.raises(DispatchAlreadyCommitted):
        journal.begin_acquire(token, ref, 0, op)
    closing = journal.advance(token, "closing", (proof,), 2, cleanup(token, "closing"))
    closed = journal.advance(
        token, "closed", (proof,), closing.revision, cleanup(token, "closed")
    )
    assert closed.state == "closed" and closed.revision == 4


def test_no_legacy_direct_acquire_or_generic_acquiring(tmp_path: Path) -> None:
    journal, token, proof = prepare(tmp_path)
    prior = journal.register(token, context(token))
    with pytest.raises(InvalidTransition):
        journal.advance(token, "acquired", (proof,), 0, context(token, "skip"))
    with pytest.raises(OwnershipConflict):
        journal.advance(token, "acquiring", (proof,), 0, context(token, "bypass"))
    assert journal.read(token, context(token, "read")) == prior


def test_lost_acquisition_ack_does_not_allow_second_starter(tmp_path: Path) -> None:
    journal, token, proof = prepare(tmp_path)
    journal.register(token, context(token))
    op = context(token, "launch")
    ref = intent(tmp_path, token, proof, op)
    # Marker/birth exist: temp fsync succeeds, publication succeeds, dir fsync fails.
    with patch(
        "lab_generate_skill.adapters.storage.atomic_snapshot.os.fsync",
        side_effect=[None, OSError("lost acquisition ack")],
    ):
        with pytest.raises(OSError) as caught:
            journal.begin_acquire(token, ref, 0, op)
    assert getattr(caught.value, "resource_candidate").state == "acquiring"
    restarted, _, _ = prepare(tmp_path)
    with pytest.raises(DispatchAlreadyCommitted):
        restarted.begin_acquire(token, ref, 0, op)
    assert restarted.read(token, context(token, "inspect")).revision == 1


@pytest.mark.parametrize(
    "missing", ["snapshot", "birth", "marker", "lock", "snapshot_and_marker"]
)
def test_used_namespace_loss_never_reinitializes_or_disappears_from_discovery(
    tmp_path: Path,
    missing: str,
) -> None:
    journal, token, proof = prepare(tmp_path)
    op = context(token)
    journal.register(token, op)
    launch = context(token, "launch")
    journal.begin_acquire(token, intent(tmp_path, token, proof, launch), 0, launch)
    stem = hashlib.sha256(token.allocation_id.encode()).hexdigest() + ".resource.json"
    paths = {
        "snapshot": stem,
        "birth": stem + ".pending-" + "0" * 64,
        "marker": stem + ".initialized",
        "lock": stem + ".lock",
    }
    for key in (
        ["snapshot", "marker"] if missing == "snapshot_and_marker" else [missing]
    ):
        (tmp_path / paths[key]).unlink()
    with pytest.raises(EvidenceIntegrityError):
        journal.register(token, op)
    with pytest.raises((EvidenceIntegrityError, EvidenceNotFound)):
        journal.records(token.owner, context(token, "discover"))
    assert not (
        tmp_path / paths[missing if missing != "snapshot_and_marker" else "snapshot"]
    ).exists()


def test_old_namespace_cannot_start_parallel_empty_history(tmp_path: Path) -> None:
    journal, token, _ = prepare(tmp_path)
    old = tmp_path / (
        hashlib.sha256(token.allocation_id.encode()).hexdigest() + ".json"
    )
    old.write_text('{"schema_version":"resource-record/1"}')
    with pytest.raises(EvidenceIntegrityError):
        journal.register(token, context(token))
    assert not list(tmp_path.glob("*.resource.json"))
    with pytest.raises(EvidenceIntegrityError):
        journal.records(token.owner, context(token, "discover"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", "cleanup"),
        ("allocation_id", "other"),
        ("owner_id", "other"),
        ("recovery_ref", None),
    ],
)
def test_acquisition_intent_rejects_foreign_context(
    tmp_path: Path, field: str, value: object
) -> None:
    _, token, proof = prepare(tmp_path)
    op = context(token, "launch").model_copy(
        update={field: value, "parent_operation_id": "parent"}
    )
    with pytest.raises(ValidationError):
        ResourceAcquisitionIntent(token=token, operation=op, configuration_ref=proof)


def test_original_operation_cannot_change_deadline_after_restart(
    tmp_path: Path,
) -> None:
    journal, token, proof = prepare(tmp_path)
    registered = context(token)
    journal.register(token, registered)
    op = context(token, "launch")
    ref = intent(tmp_path, token, proof, op)
    journal.begin_acquire(token, ref, 0, op)
    restarted, _, _ = prepare(tmp_path)
    changed = context(token, "launch")
    with pytest.raises(OwnershipConflict):
        restarted.begin_acquire(token, ref, 0, changed)
    with pytest.raises(OwnershipConflict):
        restarted.register(token, context(token))


def _starter(root: str, token_raw: str, proof_raw: str, index: int) -> None:
    path = Path(root)
    token, proof = AllocationToken.model_validate_json(
        token_raw
    ), EvidenceRef.model_validate_json(proof_raw)
    journal = FileResourceJournal(
        path,
        token.owner,
        OperationGuards(SystemClock(), NoCancellation()),
        FileEvidenceStore(path),
    )
    op = context(token, f"starter-{index}")
    ref = intent(path, token, proof, op)
    try:
        journal.begin_acquire(token, ref, 0, op)
        # Stand-in provider effect, performed only by the sole acknowledged caller.
        (path / f"effect-{index}").write_text(str(os.getpid()))
        outcome = "started"
    except RevisionConflict:
        outcome = "refused"
    (path / f"outcome-{index}").write_text(outcome)


def test_competing_independent_processes_have_one_effect(tmp_path: Path) -> None:
    journal, token, proof = prepare(tmp_path)
    journal.register(token, context(token))
    pool = multiprocessing.get_context("spawn")
    processes = [
        pool.Process(
            target=_starter,
            args=(str(tmp_path), token.model_dump_json(), proof.model_dump_json(), i),
        )
        for i in range(3)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        if process.is_alive():
            process.terminate()
            process.join(5)
            pytest.fail("Acquisition race exceeded test bound")
        assert process.exitcode == 0
    assert len(list(tmp_path.glob("effect-*"))) == 1
    assert [p.read_text() for p in tmp_path.glob("outcome-*")].count("refused") == 2
    assert journal.read(token, context(token, "inspect")).state == "acquiring"


@pytest.mark.parametrize("revision", [True, None, -1, "0", 0.0, [], {}])
def test_invalid_acquisition_revision_has_no_resource_event(
    tmp_path: Path, revision: object
) -> None:
    journal, token, proof = prepare(tmp_path)
    prior = journal.register(token, context(token))
    op = context(token, "launch")
    ref = intent(tmp_path, token, proof, op)
    with pytest.raises(ValueError):
        journal.begin_acquire(token, ref, cast(int, revision), op)
    assert journal.read(token, context(token, "inspect")) == prior


@pytest.mark.parametrize(
    "fault",
    [
        "configuration_missing",
        "intent_missing",
        "wrong_schema",
        "foreign_operation",
        "cleanup",
    ],
)
def test_invalid_stored_acquisition_does_not_commit(tmp_path: Path, fault: str) -> None:
    journal, token, proof = prepare(tmp_path)
    prior = journal.register(token, context(token))
    op = context(token, "launch")
    ref = intent(tmp_path, token, proof, op)
    expected: type[Exception] = OwnershipConflict
    if fault == "configuration_missing":
        (tmp_path / "blobs" / proof.sha256).unlink()
        expected = EvidenceNotFound
    elif fault == "intent_missing":
        (tmp_path / "blobs" / ref.sha256).unlink()
        expected = EvidenceNotFound
    elif fault == "wrong_schema":
        ref = proof
    elif fault == "foreign_operation":
        op = context(token, "other-launch")
    else:
        op = cleanup(token, "cleanup-launch")
    with pytest.raises(expected):
        journal.begin_acquire(token, ref, 0, op)
    assert journal.read(token, context(token, "inspect")) == prior


def test_legacy_lock_without_snapshot_blocks_new_namespace(tmp_path: Path) -> None:
    journal, token, _ = prepare(tmp_path)
    old_lock = tmp_path / (
        hashlib.sha256(token.allocation_id.encode()).hexdigest() + ".json.lock"
    )
    old_lock.touch()
    with pytest.raises(EvidenceIntegrityError):
        journal.register(token, context(token))
    assert not list(tmp_path.glob("*.resource.json*"))
    with pytest.raises(EvidenceIntegrityError):
        journal.records(token.owner, context(token, "discover"))
