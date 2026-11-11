"""Original failure capture and partial/unknown process facts remain exact."""

import base64
import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.capture import CommandCapture, CommandFailure
from lab_generate_skill.domain.process_identity import ProcessTermination
from shopping_native_diagnostics import retain_native_failure


@pytest.mark.parametrize("ending", ["reaped", "unconfirmed"])
def test_original_command_bytes_and_actual_termination_retained(
    tmp_path: Path, ending: str
) -> None:
    termination = (
        ProcessTermination(3100, "reaped", 1, False)
        if ending == "reaped"
        else ProcessTermination(3100, "unconfirmed", None, False)
    )
    capture = CommandCapture(
        ("/native", "private"),
        termination.returncode,
        b"out\x00",
        b"actual failure\xff",
        ending == "reaped",
        termination,
    )
    error = CommandFailure("NATIVE_COMMAND_FAILED", capture)
    path = retain_native_failure(tmp_path, error)
    assert path is not None
    actual = json.loads(path.read_text())
    assert base64.b64decode(actual["stdout_base64"]) == capture.stdout
    assert base64.b64decode(actual["stderr_base64"]) == capture.stderr
    assert actual["termination"]["state"] == ending and actual["argv"] == [
        "/native",
        "private",
    ]
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        retain_native_failure(tmp_path, error)


def test_non_command_error_is_not_fabricated(tmp_path: Path) -> None:
    assert retain_native_failure(tmp_path, ValueError("fixture error")) is None
    assert not list(tmp_path.iterdir())
