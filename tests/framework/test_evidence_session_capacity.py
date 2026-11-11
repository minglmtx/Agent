"""Closure budget and prior-prefix validation, independent of disk persistence."""

import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionCapacity,
    MAX_OUTCOME_BYTES,
    MAX_RESOLUTION_BYTES,
)
from lab_generate_skill.domain.evidence_session_state import (
    EvidenceSessionSnapshot,
    begin_evidence_exchange,
    record_evidence_outcome,
    resolve_evidence_exchange,
)
from lab_generate_skill.domain.errors import JournalCapacityExceeded
from evidence_session_fixtures import (
    binding,
    capacity,
    intent,
    outcome,
    resolution,
    pending,
)


def test_exact_prefix_closure_reserve_and_one_byte_below() -> None:
    snapshot = pending()
    limit = 100000
    # Independent serialized-size calculation; resolve decimal-field-width change.
    for _ in range(5):
        proposed = snapshot.model_copy(
            update={"capacity": capacity().model_copy(update={"max_bytes": limit})}
        )
        needed = (
            len(proposed.model_dump_json().encode())
            + MAX_OUTCOME_BYTES
            + 3 * (MAX_RESOLUTION_BYTES + 1)
        )
        if needed == limit:
            break
        limit = needed
    exact = EvidenceSessionSnapshot.model_validate(proposed)
    assert (
        len(exact.model_dump_json().encode())
        + MAX_OUTCOME_BYTES
        + 3 * (MAX_RESOLUTION_BYTES + 1)
        == limit
    )
    with pytest.raises((ValidationError, JournalCapacityExceeded)):
        EvidenceSessionSnapshot.model_validate(
            exact.model_copy(
                update={
                    "capacity": exact.capacity.model_copy(
                        update={"max_bytes": limit - 1}
                    )
                }
            )
        )
    snapshot = record_evidence_outcome(exact, outcome(intent()), exact.revision)
    for n in (1, 2):
        snapshot = resolve_evidence_exchange(
            snapshot,
            resolution(
                intent(), n, ended=False, object_state="unknown", cleanup_state="failed"
            ),
            snapshot.revision,
        )
    snapshot = resolve_evidence_exchange(
        snapshot, resolution(intent(), 3), snapshot.revision
    )
    assert snapshot.entries[-1].reusable


def test_terminal_snapshot_cannot_hide_earlier_insufficient_reserve() -> None:
    snapshot = resolve_evidence_exchange(pending(), resolution(intent()), 1)
    assert len(snapshot.model_dump_json().encode()) < 8192
    with pytest.raises((ValidationError, JournalCapacityExceeded)):
        EvidenceSessionSnapshot.model_validate(
            snapshot.model_copy(
                update={"capacity": capacity().model_copy(update={"max_bytes": 8192})}
            )
        )


def test_exchange_limit_does_not_prevent_last_closure() -> None:
    cap = capacity().model_copy(update={"max_exchanges": 1})
    snapshot = begin_evidence_exchange(
        EvidenceSessionSnapshot(binding=binding(), capacity=cap), intent(), 0
    )
    snapshot = record_evidence_outcome(
        snapshot, outcome(intent(), succeeded=False), snapshot.revision
    )
    snapshot = resolve_evidence_exchange(
        snapshot, resolution(intent(), object_state="absent"), snapshot.revision
    )
    assert snapshot.entries[-1].reusable
    with pytest.raises((ValidationError, JournalCapacityExceeded)):
        begin_evidence_exchange(snapshot, intent(2), snapshot.revision)


def test_resolution_exhaustion_retains_quarantine_and_original_history() -> None:
    snapshot = pending()
    for n in (1, 2, 3):
        snapshot = resolve_evidence_exchange(
            snapshot, resolution(intent(), n, ended=False), snapshot.revision
        )
    before = snapshot.model_dump_json()
    with pytest.raises((ValidationError, JournalCapacityExceeded)):
        resolve_evidence_exchange(snapshot, resolution(intent(), 4), snapshot.revision)
    assert (
        snapshot.model_dump_json() == before
        and snapshot.entries[-1].stage == "quarantined"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_exchanges", 0),
        ("max_exchanges", 10001),
        ("max_exchanges", True),
        ("max_resolutions_per_exchange", 0),
        ("max_resolutions_per_exchange", 33),
        ("max_resolutions_per_exchange", "3"),
        ("max_bytes", 4095),
        ("max_bytes", 8 * 1024 * 1024 + 1),
        ("max_bytes", None),
    ],
)
def test_capacity_type_and_extreme_bounds(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        EvidenceSessionCapacity.model_validate(
            capacity().model_copy(update={field: value})
        )


def test_empty_snapshot_is_not_permission_to_skip_first_reserve() -> None:
    snapshot = EvidenceSessionSnapshot(
        binding=binding(), capacity=capacity().model_copy(update={"max_bytes": 4096})
    )
    assert snapshot.revision == 0 and snapshot.entries == ()
    with pytest.raises((ValidationError, JournalCapacityExceeded)):
        begin_evidence_exchange(snapshot, intent(), 0)
