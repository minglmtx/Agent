"""Explicit reuse of passed cases from an identical frozen check version."""

import json
from pathlib import Path
from typing import Any
from framework_checks.cache import file_digest


def previously_passed(
    receipts: list[Path], files: dict[str, str], environment_key: str
) -> tuple[list[str], list[dict[str, str]]]:
    nodes: set[str] = set()
    evidence = []
    for path in receipts:
        value: Any = json.loads(path.read_text())
        if (
            value.get("schema_version") != "framework-check/3"
            or value.get("passed") is not True
            or value.get("source_stable_during_checks") is not True
            or value.get("files") != files
            or value.get("environment_key") != environment_key
        ):
            raise ValueError(
                "Passed-case reuse requires an identical successful frozen check"
            )
        cases = path.parent / "selected-cases.json"
        if file_digest(cases) != value.get("selected_cases_sha256"):
            raise ValueError("Passed-case evidence changed")
        recorded = json.loads(cases.read_text())
        if recorded["schema_version"] != "check-cases/1" or recorded["exitstatus"] != 0:
            raise ValueError("Unsuccessful selected tests cannot be reused")
        for node in recorded["passed"]:
            if (
                not isinstance(node, str)
                or not node.startswith("tests/framework/")
                or "::" not in node
            ):
                raise ValueError("Invalid recorded node ID")
            nodes.add(node)
        evidence.append({"path": str(path), "sha256": file_digest(path)})
    return sorted(nodes), evidence
