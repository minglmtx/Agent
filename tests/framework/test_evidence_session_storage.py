"""Actual file state, immutable bindings and read-only diagnostics."""

from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    EvidenceIntegrityError,
    EvidenceNotFound,
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceSessionCapacity,
)
from lab_generate_skill.ports.evidence_sessions import EvidenceSessions
from evidence_session_fixtures import binding, capacity, intent, outcome, resolution
from evidence_session_storage_fixtures import store, snapshot_path, UnitSessionAuthority


def test_persist_reopen_exact_facts_and_next_exchange(tmp_path: Path) -> None:
    ledger: EvidenceSessions = store(tmp_path)
    b, c, original = binding(), capacity(), intent()
    empty = ledger.create(b, c, original.operation)
    assert empty.revision == 0
    assert ledger.create(b, c, original.operation) == empty
    pending = ledger.begin(b, original, 0)
    assert store(tmp_path).read(b, original.operation) == pending
    with pytest.raises(DispatchAlreadyCommitted):
        store(tmp_path).begin(b, original, 0)
    with pytest.raises(InvalidTransition):
        store(tmp_path).begin(b, intent(2), 1)
    returned = store(tmp_path).record_outcome(
        b, outcome(original), 1, original.operation
    )
    assert returned.entries[0].stage == "returned"
    assert (
        store(tmp_path).record_outcome(b, outcome(original), 0, original.operation)
        == returned
    )
    closed = store(tmp_path).resolve(b, resolution(original), 2)
    assert closed.entries[0].reusable
    assert store(tmp_path).resolve(b, resolution(original), 0) == closed
    assert store(tmp_path).begin(b, intent(2), 3).revision == 4


def test_missing_read_has_no_disk_effects(tmp_path: Path) -> None:
    with pytest.raises(EvidenceIntegrityError):
        store(tmp_path).read(binding(), intent().operation)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", "new-session"),
        ("release_id", "new-release"),
        ("storage_config_sha256", "f" * 64),
    ],
)
def test_binding_cannot_be_rebound(tmp_path: Path, field: str, value: str) -> None:
    ledger = store(tmp_path)
    b = binding()
    op = intent().operation
    ledger.create(b, capacity(), op)
    before = snapshot_path(tmp_path).read_bytes()
    changed = EvidenceSessionBinding.model_validate({**b.model_dump(), field: value})
    with pytest.raises(OwnershipConflict):
        ledger.create(changed, capacity(), op)
    assert snapshot_path(tmp_path).read_bytes() == before


def test_capacity_cannot_change_or_unknown_intent_repeat(tmp_path: Path) -> None:
    ledger = store(tmp_path)
    b = binding()
    original = intent()
    ledger.create(b, capacity(), original.operation)
    larger = EvidenceSessionCapacity.model_validate(
        {**capacity().model_dump(), "max_exchanges": 4}
    )
    with pytest.raises(OwnershipConflict):
        ledger.create(b, larger, original.operation)
    with pytest.raises(RevisionConflict):
        ledger.begin(b, original, 10)
    assert ledger.read(b, original.operation).revision == 0


@pytest.mark.parametrize(
    "damage",
    [
        "missing_snapshot",
        "missing_marker",
        "missing_both",
        "missing_birth",
        "bad_json",
        "duplicate_json",
        "oversize",
    ],
)
def test_damaged_used_namespace_never_reinitialized(
    tmp_path: Path, damage: str
) -> None:
    ledger = store(tmp_path)
    b = binding()
    op = intent().operation
    ledger.create(b, capacity(), op)
    path = snapshot_path(tmp_path)
    if damage == "missing_snapshot":
        path.unlink()
    elif damage == "missing_marker":
        Path(str(path) + ".initialized").unlink()
    elif damage == "missing_both":
        path.unlink()
        Path(str(path) + ".initialized").unlink()
    elif damage == "missing_birth":
        Path(str(path) + ".pending-" + "0" * 64).unlink()
    elif damage == "bad_json":
        path.write_bytes(b"[]")
    elif damage == "duplicate_json":
        path.write_bytes(b'{"entries":[],"entries":[]}')
    else:
        path.write_bytes(b"x" * (8 * 1024 * 1024 + 1))
    before = {p.name: p.stat().st_size for p in tmp_path.iterdir()}
    with pytest.raises(EvidenceIntegrityError):
        ledger.create(b, capacity(), op)
    with pytest.raises((EvidenceIntegrityError, EvidenceNotFound)):
        ledger.read(b, op)
    assert {p.name: p.stat().st_size for p in tmp_path.iterdir()} == before


def test_missing_lock_is_not_repaired_by_read_or_begin(tmp_path: Path) -> None:
    ledger = store(tmp_path)
    b = binding()
    op = intent().operation
    ledger.create(b, capacity(), op)
    lock = Path(str(snapshot_path(tmp_path)) + ".lock")
    lock.unlink()
    with pytest.raises((EvidenceIntegrityError, EvidenceNotFound)):
        ledger.read(b, op)
    with pytest.raises(EvidenceIntegrityError):
        ledger.begin(b, intent(), 0)
    assert not lock.exists()


def test_authority_denial_before_any_namespace_creation(tmp_path: Path) -> None:
    authority = UnitSessionAuthority()
    authority.denied = True
    with pytest.raises(OwnershipConflict):
        store(tmp_path, authority).create(binding(), capacity(), intent().operation)
    assert not list(tmp_path.iterdir())


def test_expired_original_outcome_can_only_use_parent_cleanup(tmp_path: Path) -> None:
    from datetime import timedelta
    from lab_generate_skill.runtime.lifecycle import OperationGuards
    from lab_generate_skill.adapters.ledger.evidence_sessions import (
        FileEvidenceSessions,
    )
    from lab_generate_skill.domain.errors import OperationStopped
    from test_lifecycle import ManualClock, CancelSwitch

    clock = ManualClock()
    b = binding()
    original = intent()
    ledger = FileEvidenceSessions(
        tmp_path,
        b.storage_id,
        b.storage_config_sha256,
        OperationGuards(clock, CancelSwitch()),
        UnitSessionAuthority(),
    )
    ledger.create(b, capacity(), original.operation)
    ledger.begin(b, original, 0)
    clock.wall += timedelta(seconds=20)
    clock.elapsed += 20
    with pytest.raises(OperationStopped):
        ledger.record_outcome(b, outcome(original), 1, original.operation)
    cleanup = resolution(original).operation
    assert ledger.record_outcome(b, outcome(original), 1, cleanup).entries[
        0
    ].outcome == outcome(original)
    wrong = cleanup.model_copy(update={"parent_operation_id": "wrong"})
    with pytest.raises(ValueError):
        ledger.record_outcome(b, outcome(original), 2, wrong)


@pytest.mark.parametrize("bad", [None, "", [], True])
def test_invalid_binding_has_no_side_effects(tmp_path: Path, bad: object) -> None:
    with pytest.raises((ValidationError, TypeError)):
        store(tmp_path).create(
            cast(EvidenceSessionBinding, bad), capacity(), intent().operation
        )
    assert not list(tmp_path.iterdir())


def test_sources_have_separate_durable_state(tmp_path: Path) -> None:
    ledger = store(tmp_path)
    original = intent()
    first = binding()
    second = EvidenceSessionBinding.model_validate(
        {**first.model_dump(), "source_task_id": "source-2"}
    )
    ledger.create(first, capacity(), original.operation)
    ledger.create(second, capacity(), original.operation)
    ledger.begin(first, original, 0)
    assert ledger.read(second, original.operation).revision == 0
    assert ledger.begin(second, intent(2), 0).revision == 1
    assert ledger.read(first, original.operation).entries[0].intent == original


def test_create_does_not_repair_used_namespace_lock(tmp_path: Path) -> None:
    ledger = store(tmp_path)
    original = intent()
    ledger.create(binding(), capacity(), original.operation)
    lock = Path(str(snapshot_path(tmp_path)) + ".lock")
    lock.unlink()
    with pytest.raises(EvidenceIntegrityError):
        ledger.create(binding(), capacity(), original.operation)
    assert not lock.exists()
