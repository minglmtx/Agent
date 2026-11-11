"""Original runner capture, not typed/PID absence or successful output alone."""

from dataclasses import replace
from pathlib import Path
import pytest
from lab_generate_skill.adapters.storage.termination_capture import captured_storage_end
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from registered_storage_fixtures import request


@pytest.mark.parametrize("code", [0, 7, -9])
def test_observed_success_failure_and_kill_have_exact_original_fact(
    tmp_path: Path, code: int
) -> None:
    parent = request(tmp_path, create=True).controller
    capture = CommandCapture(
        ("/fixed/python",),
        code,
        b"original",
        b"",
        code == 0,
        ProcessTermination(123, "reaped", code, code < 0),
    )
    fact = captured_storage_end(parent, b"original request", capture.argv, capture)
    assert fact is not None and fact.process_id == 123 and fact.returncode == code
    assert fact.controller == parent and len(fact.sha256) == 64
    changed = captured_storage_end(parent, b"other request", capture.argv, capture)
    assert changed is not None and changed.request_sha256 != fact.request_sha256


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "unknown",
        "close",
        "wrong_argv",
        "wrong_code",
        "bool_code",
        "self",
        "no_capture",
    ],
)
def test_unconfirmed_capture_cannot_produce_ending(tmp_path: Path, fault: str) -> None:
    parent = request(tmp_path, create=True).controller
    capture = CommandCapture(
        ("/fixed/python",),
        0,
        b"",
        b"",
        True,
        ProcessTermination(123, "reaped", 0, False),
    )
    if fault == "missing":
        capture = replace(capture, termination=None)
    elif fault == "unknown":
        capture = replace(
            capture, termination=ProcessTermination(123, "unconfirmed", None, True)
        )
    elif fault == "close":
        capture = replace(
            capture,
            termination=ProcessTermination(123, "reaped", 0, False, ("OSError",)),
        )
    elif fault == "wrong_argv":
        capture = replace(capture, argv=("/other/python",))
    elif fault == "wrong_code":
        capture = replace(capture, returncode=1)
    elif fault == "bool_code":
        capture = replace(capture, returncode=False)
    elif fault == "self":
        capture = replace(
            capture,
            termination=ProcessTermination(parent.process_id, "reaped", 0, False),
        )
    assert (
        captured_storage_end(
            parent,
            b"request",
            ("/fixed/python",),
            None if fault == "no_capture" else capture,
        )
        is None
    )
