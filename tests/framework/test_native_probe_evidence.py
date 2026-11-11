"""Original native failure content survives grouping and remains independently readable."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.capture import CommandCapture, CommandFailure
from lab_generate_skill.domain.process_identity import ProcessTermination
from native_probe_evidence import preserve_failure


@pytest.mark.parametrize("grouped", [False, True])
def test_original_command_and_complete_traceback_retained(
    tmp_path: Path, grouped: bool
) -> None:
    original = CommandFailure(
        "NATIVE_COMMAND_FAILED",
        CommandCapture(
            ("fixed-command",),
            2,
            b"partial",
            b"{original error}\n",
            True,
            ProcessTermination(123, "reaped", 2, False),
        ),
    )
    error: BaseException = (
        ExceptionGroup("cleanup also failed", [original, OSError("cleanup")])
        if grouped
        else original
    )
    facts = preserve_failure(tmp_path, error)
    assert (tmp_path / facts["stdout"]).read_bytes() == b"partial"
    assert (tmp_path / facts["stderr"]).read_bytes() == b"{original error}\n"
    assert facts["returncode"] == 2 and facts["complete"] is True
    assert facts["termination"]["state"] == "reaped"
    trace = (tmp_path / facts["traceback"]).read_text()
    assert "NATIVE_COMMAND_FAILED" in trace
    if grouped:
        assert "cleanup" in trace
