"""Private bounded native error evidence survives RPC without expanding its schema."""

import base64
import json
import pytest
from lab_generate_skill.adapters.processes.capture import CommandCapture, CommandFailure
from lab_generate_skill.adapters.sites.worker_diagnostics import native_failure
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
from site_worker_fixtures import case, operation
from test_slurm_commands import guard


@pytest.mark.parametrize("size", [0, 5, 8192, 8193])
def test_native_stderr_bound_without_command_or_private_input(
    capsys: pytest.CaptureFixture[str], size: int
) -> None:
    error = CommandFailure(
        "NATIVE_COMMAND_FAILED",
        CommandCapture(("/secret/argv",), 2, b"secret stdout", b"x" * size, True),
    )
    native_failure(error)
    captured = capsys.readouterr()
    assert not captured.out and "secret" not in captured.err
    event = json.loads(captured.err.removeprefix("SITE_NATIVE_FAILURE "))
    assert base64.b64decode(event["stderr_base64"]) == b"x" * min(size, 8192)
    assert event["stderr_truncated"] == (size > 8192)
    assert event["returncode"] == 2


@pytest.mark.parametrize("broken", [False, True])
def test_worker_native_failure_keeps_primary_and_runs_original_cleanup(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], broken: bool
) -> None:
    import sys

    instance, service, channel, client, authority = case()
    error = CommandFailure(
        "NATIVE_COMMAND_FAILED",
        CommandCapture(("/native",), 2, b"", b"original native error", True),
    )

    def start(control: object) -> None:
        instance.calls.append("start")
        raise error

    class Broken:
        def write(self, text: str) -> None:
            raise OSError("diagnostic unavailable")

    monkeypatch.setattr(instance, "start", start)
    if broken:
        monkeypatch.setattr(sys, "stderr", Broken())
    op = operation(client.configuration)
    client.configure(op, control=guard())
    with pytest.raises(SiteWorkerFailure):
        client.start(op, control=guard())
    assert instance.calls == ["start", "stop"] and service.closed
    assert service.exits is not None
    if broken:
        assert isinstance(getattr(error, "site_diagnostic_error"), OSError)
    else:
        assert "SITE_NATIVE_FAILURE" in capsys.readouterr().err
