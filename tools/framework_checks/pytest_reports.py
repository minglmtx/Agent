"""Persist exact completed pytest phases, including interrupted sessions."""

import json
import os
from pathlib import Path
import pytest

_outcomes: dict[str, list[str]] = {}


def _write(exitstatus: int | None) -> None:
    destination = os.environ.get("LAB_CHECK_CASES_PATH")
    if not destination:
        return
    target = Path(destination)
    pending = target.with_name(target.name + ".pending")
    pending.write_text(
        json.dumps(
            {
                "schema_version": "check-cases/1",
                "exitstatus": exitstatus,
                "session_finished": exitstatus is not None,
                "passed": sorted(
                    node
                    for node, phases in _outcomes.items()
                    if phases == ["setup:passed", "call:passed", "teardown:passed"]
                ),
                "outcomes": _outcomes,
            },
            indent=2,
        )
        + "\n"
    )
    pending.replace(target)


def pytest_sessionstart(session: pytest.Session) -> None:
    _outcomes.clear()
    _write(None)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    _outcomes.setdefault(report.nodeid, []).append(f"{report.when}:{report.outcome}")
    _write(None)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    _write(exitstatus)
