"""A killed pytest child must retain only complete successful node evidence."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time


def child_command(test: Path) -> list[str]:
    return [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        str(test),
        "-p",
        "framework_checks.pytest_reports",
        "-q",
    ]


def test_teardown_failure_is_excluded_and_completed_session_is_recorded(
    tmp_path: Path,
) -> None:
    test = tmp_path / "test_child.py"
    test.write_text(
        "import pytest\n"
        "def test_good(): pass\n"
        "@pytest.fixture\n"
        "def broken():\n"
        "    yield\n"
        "    raise RuntimeError('synthetic teardown failure')\n"
        "def test_bad(broken): pass\n"
    )
    receipt = tmp_path / "cases.json"
    result = subprocess.run(
        child_command(test),
        cwd=tmp_path,
        env={**os.environ, "LAB_CHECK_CASES_PATH": str(receipt)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20,
        check=False,
    )
    assert result.returncode == 1, result.stdout.decode()
    saved = json.loads(receipt.read_text())
    assert saved["session_finished"] is True and saved["exitstatus"] == 1
    assert saved["passed"] == ["test_child.py::test_good"]
    assert saved["outcomes"]["test_child.py::test_bad"] == [
        "setup:passed",
        "call:passed",
        "teardown:failed",
    ]
    assert not receipt.with_name("cases.json.pending").exists()


def test_terminated_child_retains_finished_node_and_partial_current_node(
    tmp_path: Path,
) -> None:
    test = tmp_path / "test_child.py"
    marker = tmp_path / "started"
    test.write_text(
        "import pathlib, time\n"
        "def test_finished(): pass\n"
        "def test_incomplete():\n"
        "    pathlib.Path('started').write_text('started')\n"
        "    time.sleep(60)\n"
    )
    receipt = tmp_path / "cases.json"
    child = subprocess.Popen(
        child_command(test),
        cwd=tmp_path,
        env={**os.environ, "LAB_CHECK_CASES_PATH": str(receipt)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline:
            assert child.poll() is None
            time.sleep(0.05)
        assert marker.exists(), "Child did not reach the deliberate interruption"
        child.terminate()
        child.communicate(timeout=5)
        saved = json.loads(receipt.read_text())
        assert saved["session_finished"] is False and saved["exitstatus"] is None
        assert saved["passed"] == ["test_child.py::test_finished"]
        assert saved["outcomes"]["test_child.py::test_incomplete"] == ["setup:passed"]
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)
