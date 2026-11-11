"""Original complete guard shape and fingerprint oracle, including invalid data."""

import json
from typing import Any
import pytest
from lab_generate_skill.domain.map_state import MapPersistentState
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.sites.map.state_rules import (
    database_state,
    fingerprint,
    MAX_STATE_BYTES,
)
from map_state_fixtures import SQL


def test_original_complete_state_keeps_sequence_null_and_extreme_native_values() -> (
    None
):
    value = SQL().value
    value["sequences"] = [["a", -(2**63)], ["b", 2**63 - 1], ["c", None]]
    value["changed"] = ["public.notes"]
    raw = json.dumps(value).encode()
    assert database_state(raw) == value


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        [],
        b"",
        "{}",
        b"{}",
        b"null",
        b"{",
        b"[]",
        b"NaN",
        b"{}{}",
        b" " * (MAX_STATE_BYTES + 1),
        b'{"tables":[],"tables":["users"]}',
    ],
)
def test_empty_wrong_type_malformed_duplicate_and_extreme_state(value: Any) -> None:
    with pytest.raises(ValueError):
        database_state(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tables", []),
        ("tables", ["users", "users"]),
        ("tables", [None]),
        ("tables", [True]),
        ("tables", ["x" * 64]),
        ("tables", ["bad\0name"]),
        ("tracked", []),
        ("tracked", ["users"]),
        ("changed", None),
        ("changed", ["public.missing"]),
        ("changed", [True]),
        ("changed", ["public.users", "public.users"]),
        ("sequences", {}),
        ("sequences", [["users_id_seq", True]]),
        ("sequences", [["users_id_seq", 2**63]]),
        ("sequences", [["users_id_seq", 1.0]]),
        ("sequences", [["users_id_seq", float("nan")]]),
        ("sequences", [["users_id_seq", 1], ["users_id_seq", 2]]),
        ("sequences", [["users_id_seq"]]),
        ("sequences", [[None, 1]]),
    ],
)
def test_incomplete_guard_or_sequence_never_becomes_unchanged(
    field: str, value: Any
) -> None:
    data: dict[str, Any] = dict(SQL().value)
    data[field] = value
    with pytest.raises(ValueError):
        database_state(json.dumps(data).encode())


def test_state_requires_exact_fields_and_table_order() -> None:
    for operation in ("extra", "missing", "reorder"):
        data: dict[str, Any] = dict(SQL().value)
        if operation == "extra":
            data["unexpected"] = 0
        elif operation == "missing":
            del data["sequences"]
        else:
            data["tracked"] = list(reversed(data["tables"]))
        with pytest.raises(ValueError):
            database_state(json.dumps(data).encode())
    # Native SQL collation determines ordering, not Python's lexical order.
    data = dict(SQL().value)
    data["tables"] = data["tracked"] = ["z", "A"]
    assert database_state(json.dumps(data).encode())["tables"] == ["z", "A"]


@pytest.mark.parametrize(
    "paths",
    [("public/a", "storage/b"), ("storage/a", "storage/a"), ("tmp/a",), ("public",)],
)
def test_persistent_file_wrong_order_duplicate_or_scope(paths: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        MapPersistentState(
            baseline_json="{}",
            files=tuple(
                ReleaseFile(path=p, sha256="a" * 64, size_bytes=0, executable=False)
                for p in paths
            ),
        )


@pytest.mark.parametrize(
    "baseline",
    [
        "{}",
        "[]",
        "NaN",
        '{"status":"complete","status":"complete"}',
        '{"status":"complete","full_snapshot_imported":1,"postgres_version":"11"}',
    ],
)
def test_invalid_full_baseline_never_fingerprints(baseline: str) -> None:
    with pytest.raises(ValueError):
        fingerprint(
            MapPersistentState(baseline_json=baseline, files=()),
            json.dumps(SQL().value).encode(),
        )
