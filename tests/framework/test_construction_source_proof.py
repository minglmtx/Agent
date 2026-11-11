"""Full existing source verifier on selective read; old facts never become permits."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    OwnershipConflict,
    RevisionConflict,
    OperationStopped,
)
from lab_generate_skill.domain.construction import ConstructionPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from construction_storage_fixtures import fixture
from test_run_journal import command


def test_repeated_source_proof_rechecks_permission_without_mutating_or_sealing_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = fixture(tmp_path)
    journal, op = data.journal(), command()
    initial = journal.create(data.plan, op)
    path = data.root / "journal" / journal.file.name
    raw = path.read_bytes()
    calls: list[ConstructionPlan] = []
    original = data.authority.verify_plan

    def verify(plan: ConstructionPlan, operation: OperationContext) -> None:
        calls.append(plan)
        original(plan, operation)

    monkeypatch.setattr(data.authority, "verify_plan", verify)
    assert journal.verify_source(op) == journal.verify_source(op) == initial
    assert calls == [data.plan, data.plan] and path.read_bytes() == raw
    data.authority.denied = True
    with pytest.raises(OwnershipConflict, match="claim rejected"):
        journal.verify_source(op)
    # Original read/replay remains read-only even when a new source check fails.
    assert journal.read(op) == journal.create(data.plan, op) == initial
    assert path.read_bytes() == raw


def test_source_proof_does_not_initialize_a_missing_construction(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    with pytest.raises(EvidenceNotFound):
        journal.verify_source(command())
    assert not (data.root / "journal" / journal.file.name).exists()


def test_real_appended_history_during_proof_is_preserved_and_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = fixture(tmp_path)
    journal, op = data.journal(), command()
    initial = journal.create(data.plan, op)
    original = journal.verifier.plan
    saved: list[Any] = []

    def advance(
        plan: ConstructionPlan, operation: OperationContext, control: Any
    ) -> None:
        original(plan, operation, control)
        event = data.event(initial)
        saved.append(journal.append(event, initial.revision, event.operation))

    monkeypatch.setattr(journal.verifier, "plan", advance)
    with pytest.raises(RevisionConflict, match="changed during source"):
        journal.verify_source(op)
    assert len(saved) == 1 and journal.read(op) == saved[0]


@pytest.mark.parametrize(
    "changes", [{"owner_id": "foreign"}, {"attempt_id": "foreign"}]
)
def test_source_proof_rejects_foreign_read_before_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changes: dict[str, Any]
) -> None:
    data = fixture(tmp_path)
    journal, op = data.journal(), command()
    journal.create(data.plan, op)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("foreign read reached source proof")

    monkeypatch.setattr(journal.verifier, "plan", forbidden)
    with pytest.raises(OwnershipConflict):
        journal.verify_source(op.model_copy(update=changes))


def test_source_proof_preserves_original_stop_and_does_not_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = fixture(tmp_path)
    journal, op = data.journal(), command()
    initial = journal.create(data.plan, op)
    error = OperationStopped("CANCELLED", op.operation_id)
    calls = []

    def stop(*args: Any, **kwargs: Any) -> None:
        calls.append(True)
        raise error

    monkeypatch.setattr(journal.verifier, "plan", stop)
    with pytest.raises(OperationStopped) as caught:
        journal.verify_source(op)
    assert caught.value is error and calls == [True]
    assert journal.read(op) == initial
