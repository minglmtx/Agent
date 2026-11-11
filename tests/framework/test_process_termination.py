"""Observed child exit, uncertain cleanup and already-committed side effects."""

import os
import subprocess
import time
from pathlib import Path
from typing import cast, Literal
import pytest

from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    CommandFailure,
    ProcessTermination,
    require_reaped,
    retained_capture,
)
from lab_generate_skill.adapters.processes.cleanup import finish_process
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from test_slurm_commands import cmd, guard


@pytest.mark.parametrize("code", [0, 7])
def test_complete_capture_includes_observed_child_exit(code: int) -> None:
    capture = ProcessRunner().run(
        cmd(f"import os,sys; print(os.getpid()); sys.exit({code})"), guard()
    )
    ended = require_reaped(capture)
    assert ended.process_id == int(capture.stdout)
    assert ended.state == "reaped" and ended.returncode == code
    assert not ended.kill_requested and not ended.cleanup_errors
    assert capture.returncode == code and capture.complete


@pytest.mark.parametrize("blocking", ["read", "write"])
def test_blocking_pipe_io_is_stopped_and_child_reaped(blocking: str) -> None:
    action = "os.read(r,1)" if blocking == "read" else "os.write(w,b'x'*1000000)"
    start = time.monotonic()
    with pytest.raises(CommandFailure) as caught:
        ProcessRunner(reap_timeout=0.5).run(
            cmd("import os; print(os.getpid(),flush=True); r,w=os.pipe(); " + action),
            guard(0.7),
        )
    assert time.monotonic() - start < 3
    capture = caught.value.capture
    ended = require_reaped(capture)
    assert ended.process_id == int(capture.stdout)
    assert ended.kill_requested and ended.returncode is not None
    assert caught.value.reason_code == "DEADLINE_EXCEEDED" and not capture.complete
    with pytest.raises(ProcessLookupError):
        os.kill(ended.process_id, 0)


def test_timeout_after_publication_cannot_mean_not_written(tmp_path: Path) -> None:
    path = tmp_path / "published"
    code = f"import os,time,pathlib; pathlib.Path({str(path)!r}).write_bytes(b'committed'); print(os.getpid(),flush=True); time.sleep(20)"
    with pytest.raises(CommandFailure) as caught:
        ProcessRunner(reap_timeout=0.5).run(cmd(code), guard(0.7))
    assert path.read_bytes() == b"committed"
    ended = require_reaped(caught.value.capture)
    assert ended.state == "reaped" and not caught.value.capture.complete
    assert retained_capture(caught.value) is caught.value.capture


class BadClose:
    closed = False

    def close(self) -> None:
        raise OSError("pipe close failed")


class UnconfirmedChild:
    pid = 12345
    returncode: int | None = None
    stdin = None
    stdout = BadClose()
    stderr = BadClose()
    waited: float | None = None

    def wait(self, *, timeout: float) -> int:
        self.waited = timeout
        raise subprocess.TimeoutExpired("controlled-worker", timeout)


def test_kill_wait_and_close_failures_keep_unknown_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_signal(pid: int, signal: int) -> None:
        assert pid == 12345
        raise PermissionError("signal refused")

    monkeypatch.setattr(os, "killpg", reject_signal)
    child = UnconfirmedChild()
    termination, errors = finish_process(
        cast(subprocess.Popen[bytes], child), succeeded=False, reap_timeout=0.125
    )
    assert child.waited == 0.125
    assert termination.state == "unconfirmed" and termination.returncode is None
    assert termination.kill_requested
    assert [type(e) for e in errors] == [
        PermissionError,
        subprocess.TimeoutExpired,
        OSError,
        OSError,
    ]
    capture = CommandCapture(("/worker",), None, b"published", b"", False, termination)
    with pytest.raises(CommandFailure, match="PROCESS_CLEANUP_UNCONFIRMED"):
        require_reaped(capture)


def test_kill_acknowledgement_error_does_not_erase_observed_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = os.killpg

    def kill_then_fail(pid: int, signal: int) -> None:
        original(pid, signal)
        raise OSError("kill acknowledgement lost")

    monkeypatch.setattr(os, "killpg", kill_then_fail)
    with pytest.raises(ExceptionGroup) as caught:
        ProcessRunner(max_output_bytes=1).run(
            cmd("import os,time; os.write(1,b'xx'); time.sleep(20)"), guard()
        )
    capture = retained_capture(caught.value)
    assert capture is not None and capture.termination is not None
    assert capture.termination.state == "reaped"
    assert capture.termination.cleanup_errors == ("OSError",)
    assert isinstance(caught.value.exceptions[0], CommandFailure)
    assert isinstance(caught.value.exceptions[1], OSError)
    with pytest.raises(CommandFailure):
        require_reaped(capture)


def test_start_failure_explicitly_records_no_child() -> None:
    with pytest.raises(CommandFailure) as caught:
        ProcessRunner().run(("/missing/worker",), guard())
    assert caught.value.capture.termination == ProcessTermination(
        None, "not_started", None, False
    )
    with pytest.raises(CommandFailure):
        require_reaped(caught.value.capture)


def test_missing_termination_is_not_inferred_from_zero_exit() -> None:
    capture = CommandCapture(("/worker",), 0, b"result", b"", True)
    with pytest.raises(CommandFailure):
        require_reaped(capture)
    assert retained_capture(ValueError("no command")) is None


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_supervisor_interrupt_keeps_original_stop_and_cleanup_capture(
    interrupt: type[BaseException],
) -> None:
    class InterruptControl:
        reads = 0
        underlying = guard()

        def checkpoint(self) -> float:
            self.reads += 1
            if self.reads >= 4:
                raise interrupt("supervisor stopped")
            return self.underlying.checkpoint()

        def wait(self, seconds: float) -> None:
            self.underlying.wait(seconds)

    with pytest.raises(interrupt) as caught:
        ProcessRunner().run(cmd("import time; time.sleep(20)"), InterruptControl())
    capture = retained_capture(caught.value)
    assert capture is not None and not capture.complete
    assert require_reaped(capture).kill_requested


@pytest.mark.parametrize(
    "fields",
    [
        {
            "process_id": None,
            "state": "reaped",
            "returncode": 0,
            "kill_requested": False,
        },
        {
            "process_id": True,
            "state": "reaped",
            "returncode": 0,
            "kill_requested": False,
        },
        {
            "process_id": 1,
            "state": "reaped",
            "returncode": None,
            "kill_requested": False,
        },
        {
            "process_id": 1,
            "state": "unconfirmed",
            "returncode": 0,
            "kill_requested": True,
        },
        {
            "process_id": 1,
            "state": "not_started",
            "returncode": None,
            "kill_requested": False,
        },
        {
            "process_id": 1,
            "state": "unknown",
            "returncode": None,
            "kill_requested": False,
        },
        {
            "process_id": 1,
            "state": "reaped",
            "returncode": True,
            "kill_requested": False,
        },
    ],
)
def test_impossible_termination_facts_are_rejected(fields: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ProcessTermination(
            cast(int | None, fields["process_id"]),
            cast(Literal["not_started", "reaped", "unconfirmed"], fields["state"]),
            cast(int | None, fields["returncode"]),
            cast(bool, fields["kill_requested"]),
        )


def test_repeated_runs_do_not_reuse_prior_cleanup_facts() -> None:
    runner = ProcessRunner()
    first = runner.run(cmd("print('first')"), guard())
    with pytest.raises(CommandFailure) as caught:
        runner.run(cmd("import time; time.sleep(20)"), guard(0.2))
    last = runner.run(cmd("print('last')"), guard())
    assert require_reaped(first).kill_requested is False
    assert require_reaped(caught.value.capture).kill_requested is True
    assert require_reaped(last).kill_requested is False
    assert first.stdout == b"first\n" and last.stdout == b"last\n"


def test_shared_cleanup_does_not_signal_a_child_already_reaped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = subprocess.Popen(
        cmd("pass"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    assert process.wait(timeout=5) == 0

    def forbid(pid: int, signal: int) -> None:
        raise AssertionError("A reaped PID/PGID may be reused")

    monkeypatch.setattr(os, "killpg", forbid)
    termination, errors = finish_process(process, succeeded=False, reap_timeout=0.1)
    assert errors == []
    assert termination.state == "reaped" and not termination.kill_requested
    assert process.stdout is not None and process.stdout.closed
    assert process.stderr is not None and process.stderr.closed
