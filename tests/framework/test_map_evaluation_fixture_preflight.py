"""Pure original-schema verification before the synthetic fixed-worker composition."""

import ast
import json
import traceback
from decimal import Decimal
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.sites.map.native_database import (
    DATABASE_VERSION,
    database_objects,
)
from map_evaluation_capture_fixtures import database_body
from map_terminal_request_fixtures import REGION


def test_reference_fixture_exact_native_schema_and_old_failure_reproduction() -> None:
    path = Path(
        "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-intake-20261029-v1/4850813-db-fixture-original.py"
    )
    module = ast.parse(path.read_text())
    function = next(
        n
        for n in module.body
        if isinstance(n, ast.FunctionDef) and n.name == "capture_database"
    )
    assignments: list[ast.stmt] = [
        n
        for n in function.body
        if isinstance(n, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id in ("bounds", "body") for t in n.targets
        )
    ]
    assert len(assignments) == 2

    class Selected:
        bounds = REGION

    scope: dict[str, Any] = dict(
        selected=Selected(),
        Decimal=Decimal,
        json=json,
        DATABASE_VERSION=DATABASE_VERSION,
    )
    exec(
        compile(ast.Module(body=assignments, type_ignores=[]), str(path), "exec"), scope
    )
    with pytest.raises(
        ValueError, match="Exact complete independent native DB reference required"
    ):
        try:
            database_objects(json.loads(scope["body"]), REGION)
        except ValueError:
            traceback.print_exc()
            raise
    measured = database_objects(json.loads(database_body(REGION)), REGION)
    assert (
        measured.initial_node_ids == ("1",)
        and measured.objects["node"]["1"]["version"] == "1"
    )
