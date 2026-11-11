"""Live write-ahead trace gates, capacity reserves and exact fact reconciliation."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.storage.traces import EvidenceTraceRecords
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    EvidenceIntegrityError,
    EvidenceNotFound,
    InvalidTransition,
    JournalCapacityExceeded,
    OperationStopped,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.trace_events import (
    ActionPlanned,
    GenerationObserved,
    GenerationPlanned,
    InteractionObserved,
    TraceProgressEvent,
    TraceSealed,
)
from lab_generate_skill.domain.trace_journal import (
    TraceJournalCommitUnconfirmed,
    TraceSnapshot,
)
from lab_generate_skill.domain.trace_plan import TraceCapacity
from retrieval_fixtures import reference
from test_run_journal import command
from trace_journal_fixtures import fixture


def test_live_journal_full_chain_exports_exact_previously_defined_trace(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    creation = command("create", attempt="attempt")
    snapshot = journal.create(data.plan, creation)
    assert journal.create(data.plan, creation) == snapshot
    for event in data.events():
        snapshot = journal.append(event, snapshot.revision, event.operation)
        reopened = data.journal().read(command())
        assert reopened == snapshot
        if isinstance(event, (GenerationPlanned, ActionPlanned)):
            with pytest.raises(DispatchAlreadyCommitted):
                journal.append(event, 0, event.operation)
        else:
            assert journal.append(event, 0, event.operation) == snapshot
    assert snapshot.project().sealed == data.data.trace
    trace = snapshot.project().sealed
    assert trace is not None
    records = EvidenceTraceRecords(data.store, journal.controls, data.authority)
    ref = records.publish(trace, trace.operation)
    assert records.load(ref, command()) == data.data.trace
    assert TraceSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot


@pytest.mark.parametrize("count", [1, 2, 3])
def test_pending_or_terminal_states_do_not_restart_work(
    tmp_path: Path, count: int
) -> None:
    data = fixture(tmp_path, outcomes=("returned",))
    journal = data.journal()
    snapshot = journal.create(data.plan, command("create", attempt="attempt"))
    events = data.events()
    for event in events[:count]:
        snapshot = journal.append(event, snapshot.revision, event.operation)
    before = (tmp_path / "journal" / journal.file.name).read_bytes()
    repeated = cast(GenerationPlanned, events[0]).model_copy(
        update={"operation": command("new-intent", attempt="attempt")}
    )
    with pytest.raises(InvalidTransition):
        journal.append(repeated, snapshot.revision, repeated.operation)
    if count in (1, 3):
        seal = cast(TraceSealed, events[-1])
        with pytest.raises(InvalidTransition):
            journal.append(seal, snapshot.revision, seal.operation)
    assert (tmp_path / "journal" / journal.file.name).read_bytes() == before


def test_capacity_refusal_before_new_generation_leaves_room_to_seal(
    tmp_path: Path,
) -> None:
    cap = TraceCapacity(
        max_events=5,
        max_bytes=1024 * 1024,
        max_event_bytes=32768,
        max_trace_bytes=1024 * 1024,
    )
    data = fixture(tmp_path, capacity=cap)
    journal = data.journal()
    snapshot = journal.create(data.plan, command("create", attempt="attempt"))
    events = data.events()
    for event in events[:3]:
        snapshot = journal.append(event, snapshot.revision, event.operation)
    before = (tmp_path / "journal" / journal.file.name).read_bytes()
    blobs = set((tmp_path / "evidence" / "blobs").iterdir())
    planned = events[3]
    with pytest.raises(JournalCapacityExceeded):
        journal.append(planned, snapshot.revision, planned.operation)
    assert (tmp_path / "journal" / journal.file.name).read_bytes() == before
    assert set((tmp_path / "evidence" / "blobs").iterdir()) == blobs
    stop = TraceSealed(
        operation=command("seal-capacity", attempt="attempt"),
        stop_reason="error",
        stop_evidence_ref=reference(
            {"reason": "capacity"}, "trace-stop/1", store=data.store
        ),
    )
    sealed = journal.append(stop, snapshot.revision, stop.operation).project().sealed
    assert sealed and sealed.generations == 1 and sealed.interactions == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_events", True),
        ("max_events", 4),
        ("max_bytes", 0),
        ("max_bytes", 8 * 1024 * 1024 + 1),
        ("max_event_bytes", 0),
        ("max_trace_bytes", 1),
    ],
)
def test_bad_capacity_rejected(field: str, value: object) -> None:
    original = TraceCapacity(
        max_events=128,
        max_bytes=1024 * 1024,
        max_event_bytes=32768,
        max_trace_bytes=1024 * 1024,
    )
    with pytest.raises(ValidationError):
        TraceCapacity.model_validate(original.model_copy(update={field: value}))


def test_actual_run_limits_and_initial_observation_required(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    data.plan = data.plan.model_copy(update={"max_generations": 1})
    journal = data.journal()
    with pytest.raises(OwnershipConflict, match="run task or limits"):
        journal.create(data.plan, command("create", attempt="attempt"))
    assert not (tmp_path / "journal" / journal.file.name).exists()


def test_stale_revision_bad_scope_and_mutated_intent_rejected(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    snapshot = journal.create(data.plan, command("create", attempt="attempt"))
    events = data.events()
    planned = cast(GenerationPlanned, events[0])
    snapshot = journal.append(planned, 0, planned.operation)
    observed = events[1]
    for revision in (True, -1, "1", 1.0):
        with pytest.raises(ValueError):
            journal.append(observed, cast(int, revision), observed.operation)
    with pytest.raises(RevisionConflict):
        journal.append(observed, 0, observed.operation)
    changed = planned.model_copy(
        update={"intent": planned.intent.model_copy(update={"request_id": "another"})}
    )
    with pytest.raises(OwnershipConflict):
        journal.append(changed, 1, changed.operation)
    with pytest.raises(OwnershipConflict):
        journal.read(command().model_copy(update={"owner_id": "other"}))
    with pytest.raises(OwnershipConflict):
        journal.read(command(attempt="other"))
    with pytest.raises(OwnershipConflict):
        journal.create(data.plan, command("new-create", attempt="attempt"))


def test_original_result_can_reconcile_after_its_deadline(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    snapshot = journal.create(data.plan, command("create", attempt="attempt"))
    events = data.events()
    snapshot = journal.append(events[0], 0, events[0].operation)
    result = events[1].model_copy(
        update={
            "operation": events[1].operation.model_copy(
                update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
            )
        }
    )
    with pytest.raises(OperationStopped):
        journal.append(result, 1, result.operation)
    cleanup = command(
        "reconcile", attempt="attempt", cleanup_parent=result.operation.operation_id
    )
    fixed = journal.append(result, 1, cleanup)
    assert fixed.events[-1] == result
    assert journal.append(result, 0, cleanup) == fixed
    with pytest.raises(OwnershipConflict):
        journal.append(events[2], 2, cleanup)


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_actual_response_evidence_fault_does_not_commit(
    tmp_path: Path, fault: str
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    snapshot = journal.create(data.plan, command("create", attempt="attempt"))
    events = data.events()
    snapshot = journal.append(events[0], 0, events[0].operation)
    event = cast(GenerationObserved, events[1])
    assert event.generation.response_ref
    path = tmp_path / "evidence" / "blobs" / event.generation.response_ref.sha256
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"broken")
    with pytest.raises(
        EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
    ):
        journal.append(event, 1, event.operation)
    assert journal.read(command()) == snapshot


def test_used_snapshot_missing_cannot_recreate_empty_history(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    creation = command("create", attempt="attempt")
    journal.create(data.plan, creation)
    (tmp_path / "journal" / journal.file.name).unlink()
    with pytest.raises(EvidenceIntegrityError):
        data.journal().create(data.plan, creation)


def test_actual_action_result_scope_is_checked_before_commit(tmp_path: Path) -> None:
    data = fixture(tmp_path, outcomes=("returned",))
    journal = data.journal()
    snapshot = journal.create(data.plan, command("create", attempt="attempt"))
    events = data.events()
    for event in events[:3]:
        snapshot = journal.append(event, snapshot.revision, event.operation)
    original = cast(InteractionObserved, events[3])
    bad = original.model_copy(
        update={
            "interaction": original.interaction.model_copy(
                update={"operation": command("wrong-action", attempt="attempt")}
            )
        }
    )
    with pytest.raises((OwnershipConflict, ValidationError)):
        journal.append(bad, 3, bad.operation)
    assert journal.read(command()) == snapshot


def test_authority_denial_blocks_new_work_but_not_diagnostic_replay(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path, outcomes=("returned",))
    journal = data.journal()
    snapshot = journal.create(data.plan, command("create", attempt="attempt"))
    events = data.events()
    for event in events[:2]:
        snapshot = journal.append(event, snapshot.revision, event.operation)
    data.authority.denied = True
    assert journal.read(command()) == snapshot
    assert journal.append(events[1], 0, events[1].operation) == snapshot
    with pytest.raises(OwnershipConflict, match="permission denied"):
        journal.append(events[2], 2, events[2].operation)
    assert journal.read(command()) == snapshot


def test_illegal_event_roots_and_cleanup_cannot_plan_work(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    snapshot = journal.create(data.plan, command("create", attempt="attempt"))
    event = data.events()[0]
    invalid_inputs: tuple[object, ...] = (None, [], {}, 42, {"kind": "legacy_action"})
    for invalid in invalid_inputs:
        with pytest.raises(ValidationError):
            journal.append(cast(TraceProgressEvent, invalid), 0, event.operation)
    cleanup = command(
        "cleanup-plan", attempt="attempt", cleanup_parent=event.operation.operation_id
    )
    with pytest.raises(OwnershipConflict, match="cannot register"):
        journal.append(event, 0, cleanup)
    assert journal.read(command()) == snapshot
