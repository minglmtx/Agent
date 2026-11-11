"""Strict bounded batch limits, including exact byte/event closure reserves."""

from typing import cast

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.errors import JournalCapacityExceeded
from lab_generate_skill.domain.journal_capacity import JournalCapacity


def limits() -> JournalCapacity:
    return JournalCapacity(
        max_attempts=1, max_entries=20, max_bytes=100000, max_entry_bytes=4096
    )


@pytest.mark.parametrize(
    "field", ["max_attempts", "max_entries", "max_bytes", "max_entry_bytes"]
)
@pytest.mark.parametrize("value", [None, True, False, "20", 20.0, -1, [], float("inf")])
def test_capacity_rejects_invalid_scalar(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        JournalCapacity.model_validate({**limits().model_dump(), field: value})


@pytest.mark.parametrize(
    "changes",
    [
        {"max_attempts": 901},
        {"max_entries": 19},
        {"max_entries": 10001},
        {"max_bytes": 8388609},
        {"max_entry_bytes": 0},
        {"max_bytes": 81939},
        {"schema_version": "run-journal-capacity/99"},
        {"unknown": 1},
    ],
)
def test_capacity_rejects_inconsistent_or_oversized_plan(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        JournalCapacity.model_validate({**limits().model_dump(), **changes})


def test_exact_limits_and_round_trip() -> None:
    cap = limits()
    assert cap.minimum_entries == 20
    assert JournalCapacity.model_validate_json(cap.model_dump_json()) == cap
    cap.preflight(cap.max_bytes - 20 * 4097)
    with pytest.raises(JournalCapacityExceeded):
        cap.preflight(cap.max_bytes - 20 * 4097 + 1)
    cap.check(
        entries=15, encoded_bytes=100000 - 5 * 4097, pending_closures=5, attempts=1
    )
    with pytest.raises(JournalCapacityExceeded, match="Event"):
        cap.check(entries=16, encoded_bytes=0, pending_closures=5, attempts=1)
    with pytest.raises(JournalCapacityExceeded, match="Byte"):
        cap.check(
            entries=15, encoded_bytes=100001 - 5 * 4097, pending_closures=5, attempts=1
        )
    with pytest.raises(JournalCapacityExceeded, match="attempt"):
        cap.check(entries=1, encoded_bytes=1, pending_closures=0, attempts=2)


@pytest.mark.parametrize("value", [None, False, -1, 1.0, "1"])
def test_usage_and_envelope_reject_invalid_values(value: object) -> None:
    cap = limits()
    with pytest.raises(ValueError):
        cap.preflight(cast(int, value))
    with pytest.raises(ValueError):
        cap.check(
            entries=cast(int, value), encoded_bytes=0, pending_closures=0, attempts=0
        )


def test_zero_attempt_control_run_is_explicit() -> None:
    cap = JournalCapacity(
        max_attempts=0, max_entries=9, max_bytes=100000, max_entry_bytes=4096
    )
    assert cap.minimum_entries == 9
    cap.check(entries=6, encoded_bytes=1000, pending_closures=2, attempts=0)
