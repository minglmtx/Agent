"""Differential prefix constraints, malformed histories and bounded replay work."""

from collections.abc import Callable, Iterator
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.budget_journal import (
    BudgetJournalSnapshot,
    BudgetJournalCapacity,
)
from lab_generate_skill.domain.errors import JournalCapacityExceeded
from lab_generate_skill.domain.generation import RequestRecord
from lab_generate_skill.domain.request_ledger import BudgetSnapshot, ReserveEntry
from budget_capacity_fixtures import snapshot
from budget_capacity_reference import reference_capacity


def outcome(
    check: Callable[[BudgetJournalSnapshot], None], value: BudgetJournalSnapshot
) -> tuple[type[Exception], str] | None:
    try:
        check(value)
    except JournalCapacityExceeded as error:
        return type(error), str(error)
    return None


@pytest.mark.parametrize(
    "count,events",
    [(0, ())]
    + [
        (count, events)
        for count in (1, 3, 8)
        for events in (
            (),
            ("uncertain",),
            ("succeeded",),
            ("charged_failure",),
            ("rejected_before_execution",),
            ("released_not_dispatched",),
            (
                "uncertain",
                "uncertain",
                "charged_failure",
                "charge_corrected",
                "charge_corrected",
            ),
        )
    ],
)
def test_capacity_matches_original_at_every_prefix(
    count: int, events: tuple[str, ...]
) -> None:
    value = snapshot(count, events)
    for end in range(len(value.history.entries) + 1):
        prefix = BudgetJournalSnapshot(
            capacity=value.capacity,
            dispatch_policy=value.dispatch_policy,
            history=BudgetSnapshot(
                authorization=value.history.authorization,
                entries=value.history.entries[:end],
            ),
            operations=value.operations[:end],
        )
        assert (
            outcome(BudgetJournalSnapshot.check_capacity, prefix)
            == outcome(reference_capacity, prefix)
            == None
        )


@pytest.mark.parametrize("limit", ["requests", "slots", "entry", "bytes", "envelope"])
def test_same_early_capacity_failure_as_original(limit: str) -> None:
    value = snapshot(
        2, ("uncertain", "uncertain", "charged_failure", "charge_corrected")
    )
    changes: dict[str, int] = {}
    if limit == "requests":
        changes = {"max_requests": 1}
    elif limit == "slots":
        changes = {"max_requests": 2, "max_entries": 8}
    elif limit == "entry":
        changes = {"max_entry_bytes": 100}
    elif limit == "envelope":
        changes = {"max_bytes": value.capacity.max_requests * 4 * (4096 + 2)}
    else:
        # Many billing facts eventually exhaust bytes despite few requests.
        value = snapshot(1, ("succeeded",) + ("charge_corrected",) * 24)
        changes = {"max_requests": 1, "max_bytes": 4 * (4096 + 2) + 5000}
    capacity = BudgetJournalCapacity.model_validate(
        {**value.capacity.model_dump(), **changes}
    )
    value = value.model_copy(update={"capacity": capacity})
    expected = outcome(reference_capacity, value)
    assert expected is not None
    assert outcome(BudgetJournalSnapshot.check_capacity, value) == expected


def test_settlement_room_not_hidden_by_later_terminal_result() -> None:
    value = snapshot(1, ("uncertain", "uncertain", "charged_failure"))
    value = value.model_copy(
        update={
            "capacity": BudgetJournalCapacity(
                max_requests=1, max_entries=5, max_entry_bytes=4096, max_bytes=100000
            )
        }
    )
    # Prefix with two unknown facts still needs one terminal slot, exactly five.
    value.check_capacity()
    smaller = value.model_copy(
        update={"capacity": value.capacity.model_copy(update={"max_entries": 4})}
    )
    assert outcome(BudgetJournalSnapshot.check_capacity, smaller) == outcome(
        reference_capacity, smaller
    )
    assert outcome(reference_capacity, smaller) is not None


@pytest.mark.parametrize("fault", ["duplicate", "reorder", "overspend", "numeric_type"])
def test_single_replay_still_rejects_invalid_history(fault: str) -> None:
    value = snapshot(2, ("charged_failure",))
    entries = list(value.history.entries)
    first = entries[0]
    assert isinstance(first, ReserveEntry)
    if fault == "duplicate":
        entries[1] = first
    elif fault == "reorder":
        entries[0], entries[2] = entries[2], entries[0]
    else:
        amount = first.reservation.ceiling.model_copy(
            update={"units": 1000001 if fault == "overspend" else 4.0}
        )
        entries[0] = first.model_copy(
            update={
                "reservation": first.reservation.model_copy(update={"ceiling": amount})
            }
        )
    # Explicit trusted escape hatch exercises consumer revalidation, not a valid snapshot.
    changed = value.model_copy(
        update={"history": value.history.model_copy(update={"entries": tuple(entries)})}
    )
    with pytest.raises((ValueError, ValidationError)):
        changed.check_capacity()


@pytest.mark.parametrize("count", [1, 16, 64])
def test_capacity_replays_each_entry_once_and_does_not_cache(
    count: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = snapshot(count)
    original = BudgetSnapshot.replay_changes
    visited: list[str] = []

    def tracked(self: BudgetSnapshot) -> Iterator[RequestRecord]:
        for record in original(self):
            visited.append(record.reservation.request.request_id)
            yield record

    monkeypatch.setattr(BudgetSnapshot, "replay_changes", tracked)
    raw = value.model_dump_json()
    value.check_capacity()
    assert len(visited) == count
    value.check_capacity()
    assert len(visited) == 2 * count
    assert value.model_dump_json() == raw


def test_project_and_incremental_records_preserve_first_reservation_order() -> None:
    value = snapshot(3, ("uncertain", "charged_failure", "charge_corrected"))
    changes = tuple(value.history.replay_changes())
    assert len(changes) == len(value.history.entries)
    assert [record.state for record in changes] == ["budget_reserved"] * 3 + [
        "dispatching",
        "uncertain",
        "charged_failure",
        "charged_failure",
    ]
    projected = value.history.project()
    assert tuple(r.reservation.request.request_id for r in projected) == (
        "item-0",
        "item-1",
        "item-2",
    )
    assert projected[-1] == changes[-1]


def test_missing_operation_cannot_truncate_capacity_scan() -> None:
    value = snapshot(2)
    with pytest.raises(ValueError, match="original operation"):
        value.model_copy(update={"operations": value.operations[:-1]}).check_capacity()


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_exact_entry_byte_boundary(delta: int) -> None:
    value = snapshot(1, ("charged_failure", "charge_corrected"))
    largest = max(
        len(e.model_dump_json().encode()) + len(o.model_dump_json().encode()) + 3
        for e, o in zip(value.history.entries, value.operations)
    )
    value = value.model_copy(
        update={
            "capacity": value.capacity.model_copy(
                update={"max_entry_bytes": largest + delta}
            )
        }
    )
    actual = outcome(BudgetJournalSnapshot.check_capacity, value)
    assert actual == outcome(reference_capacity, value)
    assert (actual is None) == (delta >= 0)
