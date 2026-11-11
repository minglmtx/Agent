"""Real filesystem run transactions, interleaving contracts and failure boundaries."""

import fcntl
import hashlib
import multiprocessing
from dataclasses import dataclass
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    JournalCapacityExceeded,
    EvidenceNotFound,
    OperationStopped,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.execution import (
    AttemptBinding,
    AttemptEvent,
    AttemptStage,
    ExecutionFailure,
    RunBinding,
    RunEvent,
    RunStage,
    StopReason,
    SubmissionObservation,
)
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.journal_capacity import JournalCapacity
from lab_generate_skill.domain.lifecycle import (
    CancellationRef,
    OperationContext,
    ResourceOwner,
)
from lab_generate_skill.domain.run_journal import AttemptEntry, RunEntry, RunSnapshot
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.runtime.lifecycle import OperationGuards


class CancelSwitch:
    def __init__(self) -> None:
        self.cancelled = False

    def is_cancelled(self, reference: CancellationRef) -> bool:
        return self.cancelled


def command(
    name: str | None = None,
    *,
    attempt: str | None = None,
    cleanup_parent: str | None = None,
) -> OperationContext:
    return OperationContext(
        operation_id=name or "inspect-" + uuid4().hex,
        run_id="run",
        owner_id="owner",
        attempt_id=attempt,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=60),
        mode="cleanup" if cleanup_parent else "execute",
        parent_operation_id=cleanup_parent,
    )


@dataclass
class Harness:
    root: Path
    store: FileEvidenceStore
    journal: RunJournal
    binding: RunBinding
    proof: EvidenceRef
    cancel: CancelSwitch
    capacity: JournalCapacity

    @property
    def path(self) -> Path:
        return self.root / (hashlib.sha256(b"run").hexdigest() + ".run.json")

    def initial(self) -> RunEvent:
        return RunEvent(
            stage="planned",
            operation=command("run.planned"),
            occurred_at=datetime.now(timezone.utc),
            component_id="controller",
        )

    def create(self) -> RunSnapshot:
        initial = self.initial()
        return self.journal.create(initial, initial.operation)

    def run_entry(
        self, snapshot: RunSnapshot, stage: RunStage, stop: StopReason | None = None
    ) -> RunEntry:
        run, _ = snapshot.project()
        parent = run.events[-1].operation.operation_id
        op = command(
            "run." + stage,
            cleanup_parent=parent if stage in ("closing", "sealed") else None,
        )
        observation = None
        if stage == "submitted":
            observation = SubmissionObservation(
                submission_key=self.binding.submission_key,
                outcome="accepted",
                job_ids=("job",),
                evidence=(self.proof,),
            )
        return RunEntry(
            event=RunEvent(
                stage=stage,
                operation=op,
                previous_operation_id=parent,
                occurred_at=datetime.now(timezone.utc),
                component_id="controller",
                outputs=(self.proof,),
                stop_reason=stop,
                submission=observation,
            )
        )

    def running(self) -> RunSnapshot:
        snapshot = self.create()
        for stage in ("validated", "claimed", "submitting", "submitted", "running"):
            entry = self.run_entry(snapshot, cast(RunStage, stage))
            snapshot = self.journal.append(
                entry, snapshot.revision, entry.event.operation
            )
        return snapshot

    def attempt_entry(
        self,
        snapshot: RunSnapshot,
        attempt: str,
        stage: AttemptStage,
        stop: StopReason | None = None,
    ) -> AttemptEntry:
        _, attempts = snapshot.project()
        previous = next(
            (record for record in attempts if record.binding.attempt_id == attempt),
            None,
        )
        binding = (
            previous.binding
            if previous
            else AttemptBinding(
                run=self.binding,
                attempt_id=attempt,
                claim_ref=self.proof,
                task=TaskIdentity(
                    source_task_id="source-" + attempt,
                    task_id="task-" + attempt,
                    split="train",
                    site="map",
                    family="export",
                    contract_version=1,
                ),
            )
        )
        parent = previous.events[-1].operation.operation_id if previous else None
        op = command(
            f"attempt.{attempt}.{stage}",
            attempt=attempt,
            cleanup_parent=(
                parent if stage in ("closing", "restoring", "sealed") else None
            ),
        )
        return AttemptEntry(
            binding=binding,
            event=AttemptEvent(
                stage=stage,
                operation=op,
                previous_operation_id=parent,
                occurred_at=datetime.now(timezone.utc),
                component_id="attempt",
                outputs=(self.proof,) if previous else (),
                stop_reason=stop,
            ),
        )


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    store = FileEvidenceStore(tmp_path)
    proof = store.put(
        b"Persisted fixture evidence, not scheduler authorization",
        EvidenceMetadata(
            media_type="text/plain",
            content_schema="fixture/1",
            visibility="private",
            producer="test",
        ),
    )
    binding = RunBinding(
        owner=ResourceOwner(
            run_id="run", owner_id="owner", job_id="controller", worker_id="worker"
        ),
        plan_ref=proof,
        release_ref=proof,
        submission_key="stable-key",
    )
    cancel = CancelSwitch()
    capacity = JournalCapacity(
        max_attempts=8, max_entries=128, max_bytes=2 * 1024 * 1024, max_entry_bytes=8192
    )
    journal: RunJournal = FileRunJournal(
        tmp_path,
        binding,
        OperationGuards(SystemClock(), cancel),
        store,
        capacity=capacity,
    )
    return Harness(tmp_path, store, journal, binding, proof, cancel, capacity)


def test_read_missing_run_is_side_effect_free(harness: Harness) -> None:
    before = sorted(p.name for p in harness.root.iterdir())
    with pytest.raises(EvidenceNotFound):
        harness.journal.read(command())
    assert before == sorted(p.name for p in harness.root.iterdir())


def test_create_replay_preserves_progress_and_original_bytes(harness: Harness) -> None:
    first = harness.create()
    entry = harness.run_entry(first, "validated")
    progressed = harness.journal.append(entry, first.revision, entry.event.operation)
    raw = harness.path.read_bytes()
    first_entry = first.entries[0]
    assert isinstance(first_entry, RunEntry)
    assert harness.journal.create(first_entry.event, command()) == progressed
    assert harness.journal.append(entry, 0, command()) == progressed
    assert harness.path.read_bytes() == raw
    with pytest.raises(OwnershipConflict):
        harness.journal.create(harness.initial(), command())


def test_two_attempts_share_one_revision_and_reopen_from_disk(harness: Harness) -> None:
    running = harness.running()
    a = harness.attempt_entry(running, "a", "planned")
    b = harness.attempt_entry(running, "b", "planned")
    one = harness.journal.append(a, running.revision, a.event.operation)
    with pytest.raises(RevisionConflict):
        harness.journal.append(b, running.revision, b.event.operation)
    two = harness.journal.append(b, one.revision, b.event.operation)
    assert two.revision == running.revision + 2
    assert [r.binding.attempt_id for r in two.project()[1]] == ["a", "b"]
    reopened = FileRunJournal(
        harness.root,
        harness.binding,
        OperationGuards(SystemClock(), CancelSwitch()),
        harness.store,
        capacity=harness.capacity,
    )
    assert reopened.read(command()) == two
    assert RunSnapshot.model_validate_json(two.model_dump_json()) == two


def test_global_operation_identity_conflict_across_run_and_attempt(
    harness: Harness,
) -> None:
    snapshot = harness.running()
    entry = harness.attempt_entry(snapshot, "a", "planned")
    changed = AttemptEntry.model_validate(
        {
            **entry.model_dump(),
            "event": {
                **entry.event.model_dump(),
                "operation": {
                    **entry.event.operation.model_dump(),
                    "operation_id": "run.running",
                },
            },
        }
    )
    # A fresh guard cannot hide a missing persisted cross-stream ID check.
    reopened = FileRunJournal(
        harness.root,
        harness.binding,
        OperationGuards(SystemClock(), CancelSwitch()),
        harness.store,
        capacity=harness.capacity,
    )
    with pytest.raises(OwnershipConflict):
        reopened.append(changed, snapshot.revision, changed.event.operation)
    assert harness.journal.read(command()) == snapshot


def test_closing_run_stops_attempt_work_but_allows_cleanup_then_seal(
    harness: Harness,
) -> None:
    snapshot = harness.running()
    for stage in ("planned", "acquiring", "preparing"):
        entry = harness.attempt_entry(snapshot, "a", cast(AttemptStage, stage))
        snapshot = harness.journal.append(
            entry, snapshot.revision, entry.event.operation
        )
    normal = harness.run_entry(snapshot, "closing")
    with pytest.raises(ValidationError):
        harness.journal.append(normal, snapshot.revision, normal.event.operation)
    closing = harness.run_entry(snapshot, "closing", "timeout")
    closing = RunEntry.model_validate(
        {
            **closing.model_dump(),
            "event": {
                **closing.event.model_dump(),
                "operation": {
                    **closing.event.operation.model_dump(),
                    "operation_id": "run.stop",
                },
            },
        }
    )
    snapshot = harness.journal.append(
        closing, snapshot.revision, closing.event.operation
    )
    work = harness.attempt_entry(snapshot, "a", "starting")
    with pytest.raises(ValidationError):
        harness.journal.append(work, snapshot.revision, work.event.operation)
    new = harness.attempt_entry(snapshot, "b", "planned")
    with pytest.raises(ValidationError):
        harness.journal.append(new, snapshot.revision, new.event.operation)
    early_seal = harness.run_entry(snapshot, "sealed")
    with pytest.raises(ValidationError):
        harness.journal.append(
            early_seal, snapshot.revision, early_seal.event.operation
        )
    for stage in ("closing", "restoring", "sealed"):
        entry = harness.attempt_entry(
            snapshot,
            "a",
            cast(AttemptStage, stage),
            "timeout" if stage == "closing" else None,
        )
        snapshot = harness.journal.append(
            entry, snapshot.revision, entry.event.operation
        )
    sealed = harness.journal.append(
        early_seal, snapshot.revision, early_seal.event.operation
    )
    run, attempts = sealed.project()
    assert run.stage == attempts[0].stage == "sealed"
    assert run.stop_reason == attempts[0].stop_reason == "timeout"
    assert harness.journal.append(entry, 0, command(attempt="a")) == sealed


def test_attempt_cannot_register_before_running_or_change_binding(
    harness: Harness,
) -> None:
    snapshot = harness.create()
    entry = harness.attempt_entry(snapshot, "a", "planned")
    with pytest.raises(ValidationError):
        harness.journal.append(entry, snapshot.revision, entry.event.operation)
    for stage in ("validated", "claimed", "submitting", "submitted", "running"):
        run = harness.run_entry(snapshot, cast(RunStage, stage))
        snapshot = harness.journal.append(run, snapshot.revision, run.event.operation)
    snapshot = harness.journal.append(entry, snapshot.revision, entry.event.operation)
    next_entry = harness.attempt_entry(snapshot, "a", "acquiring")
    modified = AttemptEntry.model_validate(
        {
            **next_entry.model_dump(),
            "binding": {
                **next_entry.binding.model_dump(),
                "task": {**next_entry.binding.task.model_dump(), "task_id": "another"},
            },
        }
    )
    with pytest.raises(ValidationError):
        harness.journal.append(modified, snapshot.revision, modified.event.operation)
    assert harness.journal.read(command()) == snapshot


@pytest.mark.parametrize("revision", [None, True, False, "0", 0.0, -1, [], {}])
def test_invalid_global_revision_has_no_commit(
    harness: Harness, revision: object
) -> None:
    snapshot = harness.create()
    entry = harness.run_entry(snapshot, "validated")
    raw = harness.path.read_bytes()
    with pytest.raises(ValueError):
        harness.journal.append(entry, cast(int, revision), entry.event.operation)
    assert harness.path.read_bytes() == raw


@pytest.mark.parametrize("change", ["owner", "plan", "key"])
def test_same_run_cannot_replace_frozen_binding(harness: Harness, change: str) -> None:
    harness.create()
    data = harness.binding.model_dump()
    if change == "owner":
        data["owner"] = {**harness.binding.owner.model_dump(), "owner_id": "foreign"}
    elif change == "key":
        data["submission_key"] = "changed"
    else:
        data["plan_ref"] = {
            **harness.proof.model_dump(),
            "content_schema": "different/1",
        }
    binding = RunBinding.model_validate(data)
    journal = FileRunJournal(
        harness.root,
        binding,
        OperationGuards(SystemClock(), CancelSwitch()),
        harness.store,
        capacity=harness.capacity,
    )
    op = OperationContext.model_validate(
        {**command().model_dump(), "owner_id": binding.owner.owner_id}
    )
    with pytest.raises(OwnershipConflict):
        journal.read(op)


def test_missing_evidence_prevents_initial_commit(harness: Harness) -> None:
    (harness.root / "blobs" / harness.proof.sha256).unlink()
    with pytest.raises(EvidenceNotFound):
        harness.create()
    assert not harness.path.exists()


def test_missing_transition_evidence_preserves_prior_commit(harness: Harness) -> None:
    snapshot = harness.create()
    entry = harness.run_entry(snapshot, "validated")
    (harness.root / "blobs" / harness.proof.sha256).unlink()
    with pytest.raises(EvidenceNotFound):
        harness.journal.append(entry, snapshot.revision, entry.event.operation)
    assert harness.journal.read(command()) == snapshot


@pytest.mark.parametrize(
    "fault", ["truncated", "empty", "wrong_schema", "symlink", "oversize"]
)
def test_bad_stored_snapshot_is_refused_without_repair(
    harness: Harness, fault: str
) -> None:
    snapshot = harness.create()
    if fault == "symlink":
        harness.path.unlink()
        outside = harness.root / "outside"
        outside.write_text(snapshot.model_dump_json())
        harness.path.symlink_to(outside)
    elif fault == "wrong_schema":
        harness.path.write_text(
            snapshot.model_dump_json().replace(
                "run-journal-snapshot/2", "run-journal-snapshot/99"
            )
        )
    elif fault == "oversize":
        harness.path.write_bytes(b" " * (8 * 1024 * 1024 + 1))
    else:
        harness.path.write_text("{" if fault == "truncated" else "")
    with pytest.raises(EvidenceIntegrityError):
        harness.journal.read(command())


def test_lock_symlink_and_fifo_are_refused(harness: Harness) -> None:
    import os

    lock = Path(str(harness.path) + ".lock")
    target = harness.root / "target"
    target.write_text("unchanged")
    initial = harness.initial()
    lock.symlink_to(target)
    with pytest.raises(EvidenceIntegrityError):
        harness.journal.create(initial, initial.operation)
    assert target.read_text() == "unchanged"
    lock.unlink()
    os.mkfifo(lock)
    with pytest.raises(EvidenceIntegrityError):
        harness.journal.create(initial, initial.operation)
    assert not harness.path.exists()


def test_commit_failure_and_cleanup_failure_retain_both_causes(
    harness: Harness,
) -> None:
    snapshot = harness.create()
    entry = harness.run_entry(snapshot, "validated")
    with (
        patch(
            "lab_generate_skill.adapters.ledger.run_journal.os.replace",
            side_effect=OSError("publish failed"),
        ),
        patch(
            "lab_generate_skill.adapters.ledger.run_journal.os.unlink",
            side_effect=PermissionError("cleanup failed"),
        ),
    ):
        with pytest.raises(ExceptionGroup) as failures:
            harness.journal.append(entry, snapshot.revision, entry.event.operation)
    assert [str(error) for error in failures.value.exceptions] == [
        "publish failed",
        "cleanup failed",
    ]
    assert harness.journal.read(command()) == snapshot


def test_precommit_write_failure_removes_temp_and_preserves_history(
    harness: Harness,
) -> None:
    snapshot = harness.create()
    entry = harness.run_entry(snapshot, "validated")
    with patch(
        "lab_generate_skill.adapters.ledger.run_journal.os.fsync",
        side_effect=OSError("write failed"),
    ):
        with pytest.raises(OSError, match="write failed"):
            harness.journal.append(entry, snapshot.revision, entry.event.operation)
    assert harness.journal.read(command()) == snapshot
    assert not list(harness.root.glob(".pending-run-*"))


def test_lost_commit_ack_replay_adds_no_duplicate_event(harness: Harness) -> None:
    snapshot = harness.create()
    entry = harness.run_entry(snapshot, "validated")
    with patch(
        "lab_generate_skill.adapters.ledger.run_journal.os.fsync",
        side_effect=[None, OSError("ack lost")],
    ):
        with pytest.raises(OSError, match="ack lost"):
            harness.journal.append(entry, snapshot.revision, entry.event.operation)
    current = harness.journal.read(command())
    assert current.revision == snapshot.revision + 1
    assert harness.journal.append(entry, snapshot.revision, command()) == current
    assert not list(harness.root.glob(".pending-run-*"))


def test_lock_wait_deadline_preserves_snapshot(harness: Harness) -> None:
    snapshot = harness.create()
    entry = harness.run_entry(snapshot, "validated")
    op = OperationContext.model_validate(
        {
            **entry.event.operation.model_dump(),
            "deadline": datetime.now(timezone.utc) + timedelta(seconds=0.1),
        }
    )
    entry = RunEntry.model_validate(
        {**entry.model_dump(), "event": {**entry.event.model_dump(), "operation": op}}
    )
    with Path(str(harness.path) + ".lock").open("rb") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        with pytest.raises(OperationStopped):
            harness.journal.append(entry, snapshot.revision, op)
    assert harness.journal.read(command()) == snapshot


def test_cancelled_create_does_not_create_lock_or_snapshot(harness: Harness) -> None:
    initial = harness.initial()
    op = OperationContext.model_validate(
        {
            **initial.operation.model_dump(),
            "cancellation_ref": CancellationRef(
                channel_id="cancel", run_id="run", owner_id="owner"
            ),
        }
    )
    initial = RunEvent.model_validate({**initial.model_dump(), "operation": op})
    harness.cancel.cancelled = True
    with pytest.raises(OperationStopped):
        harness.journal.create(initial, op)
    assert not harness.path.exists() and not Path(str(harness.path) + ".lock").exists()


def _race(
    root: str,
    binding_json: str,
    entry_json: str,
    revision: int,
    marker: str,
    capacity_json: str,
) -> None:
    binding = RunBinding.model_validate_json(binding_json)
    entry = AttemptEntry.model_validate_json(entry_json)
    journal = FileRunJournal(
        Path(root),
        binding,
        OperationGuards(SystemClock(), CancelSwitch()),
        FileEvidenceStore(Path(root)),
        capacity=JournalCapacity.model_validate_json(capacity_json),
    )
    try:
        journal.append(entry, revision, entry.event.operation)
        outcome = "committed"
    except RevisionConflict:
        outcome = "stale"
    Path(marker).write_text(outcome)


def test_independent_workers_contend_for_one_global_revision(harness: Harness) -> None:
    snapshot = harness.running()
    pool = multiprocessing.get_context("spawn")
    processes = []
    for index in range(4):
        entry = harness.attempt_entry(snapshot, str(index), "planned")
        processes.append(
            pool.Process(
                target=_race,
                args=(
                    str(harness.root),
                    harness.binding.model_dump_json(),
                    entry.model_dump_json(),
                    snapshot.revision,
                    str(harness.root / f"race-{index}.txt"),
                    harness.capacity.model_dump_json(),
                ),
            )
        )
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        if process.is_alive():
            process.terminate()
            process.join(5)
            pytest.fail("Run journal process exceeded test deadline")
        assert process.exitcode == 0
    results = [(harness.root / f"race-{i}.txt").read_text() for i in range(4)]
    assert results.count("committed") == 1 and results.count("stale") == 3
    final = harness.journal.read(command())
    assert final.revision == snapshot.revision + 1
    assert len(final.project()[1]) == 1


def test_normal_attempt_and_run_close_without_rewriting_prior_facts(
    harness: Harness,
) -> None:
    snapshot = harness.running()
    original = snapshot.entries
    for stage in (
        "planned",
        "acquiring",
        "preparing",
        "starting",
        "baseline_verified",
        "executing",
        "captured",
        "evaluated",
        "closing",
        "restoring",
        "sealed",
    ):
        entry = harness.attempt_entry(snapshot, "normal", cast(AttemptStage, stage))
        snapshot = harness.journal.append(
            entry, snapshot.revision, entry.event.operation
        )
    for run_stage in ("closing", "sealed"):
        run_entry = harness.run_entry(snapshot, cast(RunStage, run_stage))
        snapshot = harness.journal.append(
            run_entry, snapshot.revision, run_entry.event.operation
        )
    assert snapshot.entries[: len(original)] == original
    run, attempts = snapshot.project()
    assert run.stop_reason is None and attempts[0].stop_reason is None
    assert run.stage == attempts[0].stage == "sealed"
    assert harness.journal.read(command()) == snapshot


def test_exact_byte_limit_and_one_byte_overflow(harness: Harness) -> None:
    initial = harness.initial()
    candidate = RunSnapshot(
        binding=harness.binding,
        capacity=harness.capacity,
        entries=(RunEntry(event=initial),),
    )
    exact = len(candidate.model_dump_json().encode())
    with patch.object(FileRunJournal, "_MAX_BYTES", exact):
        snapshot = harness.journal.create(initial, initial.operation)
        assert harness.journal.read(command()) == snapshot
        entry = harness.run_entry(snapshot, "validated")
        with pytest.raises(EvidenceIntegrityError, match="size limit"):
            harness.journal.append(entry, snapshot.revision, entry.event.operation)
        assert harness.path.read_bytes() == snapshot.model_dump_json().encode()
        assert not list(harness.root.glob(".pending-run-*"))
    with patch.object(FileRunJournal, "_MAX_BYTES", exact - 1):
        with pytest.raises(EvidenceIntegrityError, match="size limit"):
            harness.journal.read(command())


def test_new_event_requires_exact_current_operation(harness: Harness) -> None:
    snapshot = harness.create()
    entry = harness.run_entry(snapshot, "validated")
    with pytest.raises(OwnershipConflict, match="exact executing"):
        harness.journal.append(entry, snapshot.revision, command())
    assert harness.journal.read(command()) == snapshot


@pytest.mark.parametrize("entries", [(), None, [], "", ({"kind": "unknown"},)])
def test_snapshot_rejects_empty_wrong_type_and_unknown_entry_kind(
    harness: Harness, entries: object
) -> None:
    with pytest.raises(ValidationError):
        RunSnapshot.model_validate(
            dict(binding=harness.binding, capacity=harness.capacity, entries=entries)
        )


def test_snapshot_rejects_reordered_global_history(harness: Harness) -> None:
    snapshot = harness.running()
    entry = harness.attempt_entry(snapshot, "a", "planned")
    snapshot = harness.journal.append(entry, snapshot.revision, entry.event.operation)
    # Local run and attempt histories are unchanged; global order is invalid.
    entries = (*snapshot.entries[:-2], snapshot.entries[-1], snapshot.entries[-2])
    with pytest.raises(ValidationError, match="running"):
        RunSnapshot(binding=harness.binding, capacity=harness.capacity, entries=entries)
    assert harness.journal.read(command()) == snapshot


def configure_capacity(harness: Harness, capacity: JournalCapacity) -> None:
    harness.capacity = capacity
    harness.journal = FileRunJournal(
        harness.root,
        harness.binding,
        OperationGuards(SystemClock(), harness.cancel),
        harness.store,
        capacity=capacity,
    )


def submit_fact(harness: Harness, snapshot: RunSnapshot, stage: RunStage) -> RunEntry:
    """Unique identities across proven-not-submitted cycles; never real submits."""
    run, _ = snapshot.project()
    previous = run.events[-1].operation.operation_id
    outcome = {
        "submission_uncertain": "uncertain",
        "confirmed_not_submitted": "confirmed_not_submitted",
        "submitted": "accepted",
    }.get(stage)
    observation = (
        SubmissionObservation.model_validate(
            {
                "submission_key": harness.binding.submission_key,
                "outcome": outcome,
                "job_ids": ("job",) if stage == "submitted" else (),
                "evidence": (harness.proof,),
            }
        )
        if outcome
        else None
    )
    return RunEntry(
        event=RunEvent(
            stage=stage,
            operation=command(f"fact-{snapshot.revision + 1}"),
            previous_operation_id=previous,
            occurred_at=datetime.now(timezone.utc),
            component_id="scheduler-fixture",
            outputs=(harness.proof,),
            submission=observation,
        )
    )


def append_entry(
    harness: Harness, snapshot: RunSnapshot, entry: RunEntry | AttemptEntry
) -> RunSnapshot:
    return harness.journal.append(entry, snapshot.revision, entry.event.operation)


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_near_full_failure_still_records_physical_cleanup_and_seal(
    harness: Harness,
    cleanup_fails: bool,
) -> None:
    configure_capacity(
        harness,
        JournalCapacity(
            max_attempts=1, max_entries=26, max_bytes=200000, max_entry_bytes=4096
        ),
    )
    snapshot = harness.create()
    for stage in ("validated", "claimed"):
        snapshot = append_entry(
            harness, snapshot, harness.run_entry(snapshot, cast(RunStage, stage))
        )
    for _ in range(3):
        for stage in ("submitting", "submission_uncertain", "confirmed_not_submitted"):
            snapshot = append_entry(
                harness, snapshot, submit_fact(harness, snapshot, cast(RunStage, stage))
            )
    for stage in ("submitting", "submitted", "running"):
        snapshot = append_entry(
            harness, snapshot, submit_fact(harness, snapshot, cast(RunStage, stage))
        )
    for stage in (
        "planned",
        "acquiring",
        "preparing",
        "starting",
        "baseline_verified",
        "executing",
    ):
        snapshot = append_entry(
            harness,
            snapshot,
            harness.attempt_entry(snapshot, "a", cast(AttemptStage, stage)),
        )
    assert len(snapshot.entries) == 21
    affected = harness.root / "task-side-effect"
    affected.write_text("partial mutation")
    prior = harness.path.read_bytes()
    rejected = harness.attempt_entry(snapshot, "a", "captured")
    with pytest.raises(JournalCapacityExceeded, match="closure reserve"):
        append_entry(harness, snapshot, rejected)
    assert harness.path.read_bytes() == prior and affected.exists()
    first_error = ExecutionFailure(
        component_id="run-journal",
        reason_code="JOURNAL_CAPACITY_EXCEEDED",
        message="Capture event rejected; retain closure reserve",
        evidence=(harness.proof,),
    )
    closing = harness.run_entry(snapshot, "closing", "blocked")
    closing = RunEntry.model_validate(
        {
            **closing.model_dump(),
            "event": {
                **closing.event.model_dump(),
                "primary_error": first_error,
            },
        }
    )
    snapshot = append_entry(harness, snapshot, closing)
    snapshot = append_entry(
        harness, snapshot, harness.attempt_entry(snapshot, "a", "closing", "blocked")
    )
    if not cleanup_fails:
        affected.unlink()
    for stage in ("restoring", "sealed"):
        entry = harness.attempt_entry(snapshot, "a", cast(AttemptStage, stage))
        if stage == "restoring" and cleanup_fails:
            failure = ExecutionFailure(
                component_id="reset-fixture",
                reason_code="RESET_FAILED",
                message="Protected file remains; isolate this resource",
                evidence=(harness.proof,),
            )
            entry = AttemptEntry.model_validate(
                {
                    **entry.model_dump(),
                    "event": {
                        **entry.event.model_dump(),
                        "cleanup_errors": (failure,),
                    },
                }
            )
        snapshot = append_entry(harness, snapshot, entry)
    snapshot = append_entry(harness, snapshot, harness.run_entry(snapshot, "sealed"))
    run, attempts = snapshot.project()
    assert len(snapshot.entries) == 26 and run.stage == attempts[0].stage == "sealed"
    assert run.stop_reason == attempts[0].stop_reason == "blocked"
    assert run.primary_error == first_error
    assert affected.exists() is cleanup_fails
    assert bool(attempts[0].cleanup_errors) is cleanup_fails
    assert harness.journal.read(command()) == snapshot


def test_byte_exhaustion_at_submission_retains_uncertain_and_closure_space(
    harness: Harness,
) -> None:
    configure_capacity(
        harness,
        JournalCapacity(
            max_attempts=0, max_entries=128, max_bytes=40000, max_entry_bytes=4096
        ),
    )
    snapshot = harness.create()
    for stage in ("validated", "claimed"):
        snapshot = append_entry(
            harness, snapshot, harness.run_entry(snapshot, cast(RunStage, stage))
        )
    rejected: RunEntry | None = None
    for _ in range(40):
        for stage in ("submitting", "submission_uncertain", "confirmed_not_submitted"):
            entry = submit_fact(harness, snapshot, cast(RunStage, stage))
            try:
                snapshot = append_entry(harness, snapshot, entry)
            except JournalCapacityExceeded:
                rejected = entry
                break
        if rejected:
            break
    assert rejected is not None
    assert len(snapshot.entries) < 128
    if snapshot.project()[0].stage == "submitting":
        snapshot = append_entry(
            harness, snapshot, submit_fact(harness, snapshot, "submission_uncertain")
        )
    snapshot = append_entry(
        harness, snapshot, harness.run_entry(snapshot, "closing", "blocked")
    )
    snapshot = append_entry(harness, snapshot, harness.run_entry(snapshot, "sealed"))
    assert harness.path.stat().st_size <= 40000
    assert snapshot.project()[0].stage == "sealed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_entries", 129),
        ("max_attempts", 9),
        ("max_entry_bytes", 8193),
        ("max_bytes", 2097153),
    ],
)
def test_capacity_is_frozen_across_reopen(
    harness: Harness, field: str, value: int
) -> None:
    snapshot = harness.create()
    changed = JournalCapacity.model_validate(
        {**harness.capacity.model_dump(), field: value}
    )
    configure_capacity(harness, changed)
    with pytest.raises(OwnershipConflict, match="capacity"):
        harness.journal.read(command())
    assert harness.path.read_bytes() == snapshot.model_dump_json().encode()


def test_preflight_counts_envelope_and_does_not_publish(harness: Harness) -> None:
    configure_capacity(
        harness,
        JournalCapacity(
            max_attempts=1, max_entries=20, max_bytes=20 * 4097, max_entry_bytes=4096
        ),
    )
    with pytest.raises(JournalCapacityExceeded, match="envelope"):
        harness.create()
    assert not harness.path.exists()


def test_encoded_entry_ceiling_is_enforced_before_commit(harness: Harness) -> None:
    snapshot = harness.create()
    entry = harness.run_entry(snapshot, "validated")
    data = entry.model_dump()
    data["event"]["outputs"] = (harness.proof,) * 100
    large = RunEntry.model_validate(data)
    with pytest.raises(JournalCapacityExceeded, match="Entry"):
        append_entry(harness, snapshot, large)
    assert harness.journal.read(command()) == snapshot


def test_legacy_snapshot_cannot_silently_acquire_capacity(harness: Harness) -> None:
    snapshot = harness.create()
    raw = snapshot.model_dump(mode="json")
    raw.pop("capacity")
    raw["schema_version"] = "run-journal-snapshot/1"
    import json

    harness.path.write_text(json.dumps(raw))
    with pytest.raises(EvidenceIntegrityError):
        harness.journal.read(command())


def test_attempt_limit_refuses_new_identity_without_consuming_closure(
    harness: Harness,
) -> None:
    configure_capacity(
        harness,
        JournalCapacity(
            max_attempts=1, max_entries=26, max_bytes=200000, max_entry_bytes=4096
        ),
    )
    snapshot = harness.running()
    snapshot = append_entry(
        harness, snapshot, harness.attempt_entry(snapshot, "a", "planned")
    )
    with pytest.raises(JournalCapacityExceeded, match="attempt budget"):
        append_entry(harness, snapshot, harness.attempt_entry(snapshot, "b", "planned"))
    assert harness.journal.read(command()) == snapshot


def test_final_small_closures_cannot_hide_earlier_reserve_violation(
    harness: Harness,
) -> None:
    configure_capacity(
        harness,
        JournalCapacity(
            max_attempts=0, max_entries=128, max_bytes=200000, max_entry_bytes=4096
        ),
    )
    snapshot = harness.create()
    for stage in ("validated", "claimed"):
        snapshot = append_entry(
            harness, snapshot, harness.run_entry(snapshot, cast(RunStage, stage))
        )
    for _ in range(10):
        for stage in ("submitting", "submission_uncertain", "confirmed_not_submitted"):
            snapshot = append_entry(
                harness, snapshot, submit_fact(harness, snapshot, cast(RunStage, stage))
            )
    snapshot = append_entry(
        harness, snapshot, harness.run_entry(snapshot, "closing", "blocked")
    )
    snapshot = append_entry(harness, snapshot, harness.run_entry(snapshot, "sealed"))
    # Final actual bytes fit; an earlier prefix cannot guarantee worst-case close.
    reduced = JournalCapacity.model_validate(
        {
            **harness.capacity.model_dump(),
            "max_bytes": len(snapshot.model_dump_json().encode()) + 100,
        }
    )
    raw = {**snapshot.model_dump(), "capacity": reduced}
    with pytest.raises(ValidationError, match="closure reserve"):
        RunSnapshot.model_validate(raw)


def test_partial_cleanup_commit_failure_leaves_history_reconcilable(
    harness: Harness,
) -> None:
    snapshot = harness.running()
    snapshot = append_entry(
        harness, snapshot, harness.attempt_entry(snapshot, "a", "planned")
    )
    snapshot = append_entry(
        harness, snapshot, harness.run_entry(snapshot, "closing", "blocked")
    )
    snapshot = append_entry(
        harness, snapshot, harness.attempt_entry(snapshot, "a", "closing", "blocked")
    )
    marker = harness.root / "physical-resource"
    marker.write_text("owned")
    marker.unlink()
    entry = harness.attempt_entry(snapshot, "a", "restoring")
    with patch(
        "lab_generate_skill.adapters.ledger.run_journal.os.replace",
        side_effect=OSError("disk unavailable"),
    ):
        with pytest.raises(OSError, match="disk unavailable"):
            append_entry(harness, snapshot, entry)
    assert not marker.exists()
    assert harness.journal.read(command()) == snapshot
    # Storage availability restored; commit the same facts, not the physical action.
    restored = append_entry(harness, snapshot, entry)
    assert restored.project()[1][0].stage == "restoring"
    assert append_entry(harness, snapshot, entry) == restored


def test_bounded_batch_records_actual_commit_and_lock_measurements(
    harness: Harness,
    record_testsuite_property: "Callable[[str, object], None]",
) -> None:
    import json
    import time
    from threading import Event, Thread

    configure_capacity(
        harness,
        JournalCapacity(
            max_attempts=2, max_entries=32, max_bytes=200000, max_entry_bytes=4096
        ),
    )
    snapshot = harness.create()
    samples: list[dict[str, float | int]] = []
    original_flock = fcntl.flock
    first_try: float | None = None
    acquired: float | None = None
    attempted = Event()

    def measured_lock(fd: int, operation: int) -> None:
        nonlocal first_try, acquired
        if first_try is None:
            first_try = time.perf_counter()
        attempted.set()
        original_flock(fd, operation)
        acquired = time.perf_counter()

    def measured_append(entry: RunEntry | AttemptEntry) -> None:
        nonlocal snapshot, first_try, acquired
        first_try = acquired = None
        started = time.perf_counter()
        snapshot = append_entry(harness, snapshot, entry)
        finished = time.perf_counter()
        assert first_try is not None and acquired is not None
        samples.append(
            {
                "entries": len(snapshot.entries),
                "bytes": harness.path.stat().st_size,
                "total_seconds": finished - started,
                "lock_wait_seconds": acquired - first_try,
                "after_lock_seconds": finished - acquired,
            }
        )

    with patch(
        "lab_generate_skill.adapters.ledger.run_journal.fcntl.flock",
        side_effect=measured_lock,
    ):
        # Hold the actual shared-filesystem lock for a bounded interval.
        with Path(str(harness.path) + ".lock").open("rb") as lock:
            original_flock(lock.fileno(), fcntl.LOCK_EX)

            def release() -> None:
                attempted.wait(2)
                time.sleep(0.05)
                original_flock(lock.fileno(), fcntl.LOCK_UN)

            worker = Thread(target=release)
            worker.start()
            try:
                measured_append(harness.run_entry(snapshot, "validated"))
            finally:
                worker.join(3)
            assert not worker.is_alive()
        for stage in ("claimed", "submitting", "submitted", "running"):
            measured_append(harness.run_entry(snapshot, cast(RunStage, stage)))
        for attempt in ("a", "b"):
            for stage in (
                "planned",
                "acquiring",
                "preparing",
                "starting",
                "baseline_verified",
                "executing",
                "captured",
                "evaluated",
                "closing",
                "restoring",
                "sealed",
            ):
                measured_append(
                    harness.attempt_entry(snapshot, attempt, cast(AttemptStage, stage))
                )
        for stage in ("closing", "sealed"):
            measured_append(harness.run_entry(snapshot, cast(RunStage, stage)))
    assert len(snapshot.entries) == 30 and len(samples) == 29
    assert all(s["bytes"] <= 200000 and s["lock_wait_seconds"] >= 0 for s in samples)
    record_testsuite_property("run_journal_bounded_batch_metrics", json.dumps(samples))
