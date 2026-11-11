"""Frozen original full selection parity; complete-output policy stays separate."""

import ast
import hashlib
import json
import re
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.sites.map.native_database_program import reference_program
from map_database_original_oracle import oracle, CAPSULE, ROOT


def original_program(bounds: object) -> str:
    original = oracle()
    pins = json.loads(CAPSULE.read_bytes())["members"]

    def add(module: str, name: str, ns: dict[str, Any]) -> None:
        rel = "src/lab_generate_skill/" + module + ".py"
        source = (ROOT / rel).read_bytes()
        assert hashlib.sha256(source).hexdigest() == pins[rel]["sha256"]
        selected: list[ast.stmt] = [
            n
            for n in ast.parse(source).body
            if isinstance(n, ast.FunctionDef) and n.name == name
        ]
        assert len(selected) == 1
        exec(
            compile(ast.Module(selected, type_ignores=[]), str(ROOT / rel), "exec"), ns
        )

    native: dict[str, Any] = dict(
        artifact=original["native"].artifact,
        json=json,
        re=re,
        VERSION="map-native-osm-expanded-database-reference-v1",
    )
    add("map_osm_native_reference", "rails_reference_program", native)
    full: dict[str, Any] = dict(
        native=SimpleNamespace(**native),
        artifact=SimpleNamespace(MAX_OBJECTS=100000),
        exact_bounds=original["exact_bounds"],
        json=json,
        MAX_UNION_OBJECTS=500000,
    )
    add("map_native_bbox_reference", "full_reference_program", full)
    result = full["full_reference_program"](bounds, "osm-expanded-request0.json")
    assert isinstance(result, str)
    return result


@pytest.mark.parametrize(
    "bounds",
    [
        ("0", "0", "0.1", "0.1"),
        ("-73.99999999999999", "40.70000000000001", "-73.9", "40.8"),
    ],
)
def test_entire_original_query_expansion_budget_and_precision_unchanged(
    bounds: object,
) -> None:
    old = original_program(bounds)
    new = reference_program(bounds, "request0", 2 * 1024**4).decode()
    old_selection, old_write = old.rsplit("File.write(", 1)
    assert new.startswith(old_selection)
    assert old_write == '"/state/osm-expanded-request0.json", JSON.generate(payload))\n'
    assert "File::EXCL" in new and "file.fsync" in new and "directory.fsync" in new
    assert "2199023255552" in new and "500001" in new and "500000" in new
    assert "Settings.max_number_of_nodes =" not in new


@pytest.mark.parametrize(
    "bounds,label,budget",
    [
        (None, "request0", 1),
        ([], "request0", 1),
        ([0, 0, 1, 1], "request0", 1),
        ([0, 0, float("nan"), 1], "request0", 1),
        ([0, 0, 10**300, 1], "request0", 1),
        ([0, 0, 0.1, 0.1], "", 1),
        ([0, 0, 0.1, 0.1], "x\n", 1),
        ([0, 0, 0.1, 0.1], "a" * 65, 1),
        ([0, 0, 0.1, 0.1], "x", True),
        ([0, 0, 0.1, 0.1], "x", 0),
        ([0, 0, 0.1, 0.1], "x", 2 * 1024**4 + 1),
    ],
)
def test_program_rejects_invalid_extreme_inputs(
    bounds: object, label: Any, budget: Any
) -> None:
    with pytest.raises(ValueError):
        reference_program(bounds, label, budget)
