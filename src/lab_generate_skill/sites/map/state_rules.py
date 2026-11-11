"""Original persistent-state fingerprint semantics with complete input checking."""

import hashlib
import json
from typing import Any
from lab_generate_skill.domain.map_state import MapPersistentState

MAX_STATE_BYTES = 4 * 1024 * 1024


def object_json(data: bytes) -> dict[str, Any]:
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in rows:
            if key in result:
                raise ValueError("Duplicate original Map state JSON field")
            result[key] = value
        return result

    def constant(value: str) -> Any:
        raise ValueError("Nonfinite original Map state JSON value")

    value = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    if type(value) is not dict:
        raise ValueError("Original Map state object required")
    return value


def identifier(value: object) -> bool:
    return (
        type(value) is str
        and 0 < len(value.encode("utf-8")) <= 63
        and "\0" not in value
    )


def database_state(data: bytes) -> dict[str, Any]:
    if type(data) is not bytes or not 0 < len(data) <= MAX_STATE_BYTES:
        raise ValueError("Complete bounded original Map SQL response required")
    value = object_json(data)
    if set(value) != {"tables", "tracked", "changed", "sequences"}:
        raise ValueError("Complete original Map state fields required")
    tables, tracked, changed, sequences = (
        value[k] for k in ("tables", "tracked", "changed", "sequences")
    )
    if (
        type(tables) is not list
        or not tables
        or not all(identifier(t) for t in tables)
        or len(tables) != len(set(tables))
        or type(tracked) is not list
        or tables != tracked
    ):
        raise ValueError("Original Map guard must cover every public table")
    if (
        type(changed) is not list
        or any(
            type(t) is not str or t not in {"public." + n for n in tables}
            for t in changed
        )
        or len(changed) != len(set(changed))
        or type(sequences) is not list
    ):
        raise ValueError("Complete original changed tables and sequences required")
    names = []
    for row in sequences:
        if (
            type(row) is not list
            or len(row) != 2
            or not identifier(row[0])
            or not (
                row[1] is None or type(row[1]) is int and -(2**63) <= row[1] < 2**63
            )
        ):
            raise ValueError("Original public sequence name/value required")
        names.append(row[0])
    if len(names) != len(set(names)):
        raise ValueError("Duplicate original public sequence")
    return value


def fingerprint(persistent: MapPersistentState, data: bytes) -> str:
    persistent = MapPersistentState.model_validate(persistent)
    state = database_state(data)
    baseline = object_json(persistent.baseline_json.encode("utf-8"))
    if (
        baseline.get("status") != "complete"
        or baseline.get("full_snapshot_imported") is not True
        or baseline.get("postgres_version") != "11"
    ):
        raise ValueError("Original full geographic baseline required")
    payload = dict(
        baseline=baseline,
        database=state,
        files=[(f.path, f.sha256) for f in persistent.files],
    )
    # Original JSON formatting and storage/public ordering are part of its proof.
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
