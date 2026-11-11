"""Encoded capacity edges and independent bounded reconciliation operations."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.construction import CallCompleted, CallPlanned
from lab_generate_skill.domain.construction_journal import ConstructionSnapshot
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped

from construction_storage_fixtures import fixture, limits
from test_run_journal import command


@pytest.mark.parametrize("margin", [-1, 0, 1])
def test_encoded_empty_shell_exact_completion_byte_boundary(
    tmp_path: Path, margin: int
) -> None:
    data = fixture(tmp_path)
    creation = command()
    progress = ConstructionProgress(plan=data.plan)
    cap = limits(max_event_bytes=1024)
    snapshot = ConstructionSnapshot(
        capacity=cap, creation_operation=creation, progress=progress
    )
    for _ in range(4):
        required = len(snapshot.model_dump_json().encode()) + 91 * 1025
        cap = cap.model_copy(update={"max_bytes": required + margin})
        snapshot = snapshot.model_copy(update={"capacity": cap})
    assert (
        cap.max_bytes - (len(snapshot.model_dump_json().encode()) + 91 * 1025) == margin
    )
    journal = data.journal(capacity=cap)
    if margin < 0:
        with pytest.raises(ValidationError, match="completion space"):
            journal.create(data.plan, creation)
        assert list((tmp_path / "journal").iterdir()) == []
    else:
        assert journal.create(data.plan, creation) == progress


@pytest.mark.parametrize("margin", [-1, 0, 1])
def test_registered_event_exact_byte_bound(tmp_path: Path, margin: int) -> None:
    data = fixture(tmp_path)
    initial = ConstructionProgress(plan=data.plan)
    event = data.event(initial)
    bound = len(event.model_dump_json().encode()) + margin
    journal = data.journal(
        capacity=limits(max_event_bytes=bound, max_bytes=2 * 1024 * 1024)
    )
    journal.create(data.plan, command())
    path = tmp_path / "journal" / journal.file.name
    before = path.read_bytes()
    if margin < 0:
        with pytest.raises(ValidationError, match="byte ceiling"):
            journal.append(event, -1, event.operation)
        assert path.read_bytes() == before
    else:
        assert journal.append(event, -1, event.operation).events == (event,)


def test_expired_result_reconciles_under_new_cleanup_deadline(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    progress = journal.create(data.plan, command())
    planned = data.event(progress)
    progress = journal.append(planned, -1, planned.operation)
    event = data.event(progress)
    assert isinstance(event, CallCompleted)
    original = event.operation.model_copy(
        update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
    )
    event = event.model_copy(update={"operation": original})
    with pytest.raises(OperationStopped):
        journal.append(event, progress.revision, original)
    cleanup = original.cleanup("reconcile", now=datetime.now(timezone.utc), seconds=30)
    saved = journal.append(event, progress.revision, cleanup)
    assert (
        saved.events[-1] == event
        and saved.events[-1].operation.deadline == original.deadline
    )
    # New bounded commands do not rewrite the recorded event or add duplicates.
    again = original.cleanup(
        "reconcile-again", now=datetime.now(timezone.utc), seconds=30
    )
    assert data.journal().append(event, progress.revision, again) == saved


def test_reconcile_parent_cannot_start_work_or_claim_another_fact(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    progress = journal.create(data.plan, command())
    event = data.event(progress)
    assert isinstance(event, CallPlanned)
    cleanup = event.operation.cleanup(
        "unit-cleanup", now=datetime.now(timezone.utc), seconds=30
    )
    with pytest.raises(OwnershipConflict, match="new construction work"):
        journal.append(event, -1, cleanup)
    saved = journal.append(event, -1, event.operation)
    # Read-only replay is permitted but carries no execution permission.
    assert journal.append(event, -1, cleanup) == saved
    result = data.event(saved)
    with pytest.raises(OwnershipConflict):
        journal.append(result, saved.revision, cleanup)
