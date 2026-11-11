"""Real subprocess transport: bounded output, stops, argv and environment."""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.slurm.commands import (
    CommandFailure,
    SlurmCommandRunner,
)
from lab_generate_skill.domain.lifecycle import CancellationRef, OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards


class Cancel:
    def __init__(self) -> None:
        self.cancelled = False

    def is_cancelled(self, reference: CancellationRef) -> bool:
        return self.cancelled


def guard(seconds: float = 5.0) -> OperationControl:
    return OperationGuards(SystemClock(), Cancel()).bind(
        OperationContext(
            operation_id="query",
            run_id="run",
            owner_id="owner",
            deadline=datetime.now(timezone.utc) + timedelta(seconds=seconds),
        )
    )


def cmd(program: str) -> tuple[str, ...]:
    return (sys.executable, "-I", "-c", program)


def test_stdout_stderr_nonzero_are_complete() -> None:
    capture = SlurmCommandRunner().run(
        cmd("import sys; print('out'); print('err',file=sys.stderr); sys.exit(7)"),
        guard(),
    )
    assert capture.stdout == b"out\n" and capture.stderr == b"err\n"
    assert capture.returncode == 7 and capture.complete


def test_no_credentials_or_shell_expansion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-only-secret")
    capture = SlurmCommandRunner().run(
        cmd(
            "import os,sys; assert 'OPENROUTER_API_KEY' not in os.environ; print(sys.argv[1]); print(os.environ['SLURM_TIME_FORMAT'])"
        )
        + ("$(not_a_command); literal",),
        guard(),
    )
    assert capture.stdout == b"$(not_a_command); literal\n%s\n"


@pytest.mark.parametrize("amount", [1, 128, 65536])
def test_exact_output_bound(amount: int) -> None:
    capture = SlurmCommandRunner(max_output_bytes=amount).run(
        cmd(f"import os; os.write(1,b'x'*{amount})"), guard()
    )
    assert len(capture.stdout) == amount and capture.complete


@pytest.mark.parametrize(
    "program",
    [
        "import os; os.write(1,b'x'*129)",
        "import os; os.write(2,b'x'*129)",
        "import os; os.write(1,b'x'*64); os.write(2,b'y'*65)",
    ],
)
def test_combined_output_limit_kills_and_retains_bounded_prefix(program: str) -> None:
    with pytest.raises(CommandFailure) as caught:
        SlurmCommandRunner(max_output_bytes=128).run(cmd(program), guard())
    assert caught.value.reason_code == "OUTPUT_LIMIT"
    capture = caught.value.capture
    assert len(capture.stdout) + len(capture.stderr) == 128 and not capture.complete


def test_timeout_keeps_partial_output_and_reaps_child(tmp_path: Path) -> None:
    pidfile = tmp_path / "pid"
    program = f"import os,time,pathlib; pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); os.write(1,b'prefix'); time.sleep(20)"
    before = time.monotonic()
    with pytest.raises(CommandFailure) as caught:
        SlurmCommandRunner().run(cmd(program), guard(0.6))
    assert time.monotonic() - before < 4
    assert caught.value.reason_code == "DEADLINE_EXCEEDED"
    assert caught.value.capture.stdout == b"prefix"
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


def test_descendant_holding_pipe_does_not_hang_transport(tmp_path: Path) -> None:
    pidfile = tmp_path / "child"
    program = f"import os,time,pathlib; p=os.fork(); pathlib.Path({str(pidfile)!r}).write_text(str(p)) if p else None; time.sleep(20) if p==0 else os._exit(0)"
    with pytest.raises(CommandFailure):
        SlurmCommandRunner().run(cmd(program), guard(0.6))
    child = int(pidfile.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            status = Path(f"/proc/{child}/stat").read_text().split(") ")[1].split()[0]
        except (FileNotFoundError, ProcessLookupError):
            break
        if status == "Z":
            break
        time.sleep(0.01)
    else:
        pytest.fail("command descendant still active after group cleanup")


def test_live_cancellation_interrupts_transport() -> None:
    class CancelAfterPolling(Cancel):
        reads = 0

        def is_cancelled(self, reference: CancellationRef) -> bool:
            self.reads += 1
            return self.reads >= 4

    op = OperationContext(
        operation_id="cancel-query",
        run_id="run",
        owner_id="owner",
        cancellation_ref=CancellationRef(
            channel_id="cancel", run_id="run", owner_id="owner"
        ),
        deadline=datetime.now(timezone.utc) + timedelta(seconds=10),
    )
    control = OperationGuards(SystemClock(), CancelAfterPolling()).bind(op)
    before = time.monotonic()
    with pytest.raises(CommandFailure) as caught:
        SlurmCommandRunner().run(cmd("import time; time.sleep(20)"), control)
    assert caught.value.reason_code == "CANCELLED"
    assert time.monotonic() - before < 4


def test_primary_and_process_cleanup_error_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_killpg = os.killpg

    def kill_then_error(pid: int, sig: int) -> None:
        real_killpg(pid, sig)
        raise OSError("cleanup acknowledgement failed")

    monkeypatch.setattr(os, "killpg", kill_then_error)
    with pytest.raises(ExceptionGroup) as caught:
        SlurmCommandRunner(max_output_bytes=1).run(
            cmd("import os,time; os.write(1,b'xx'); time.sleep(20)"), guard()
        )
    assert isinstance(caught.value.exceptions[0], CommandFailure)
    assert caught.value.exceptions[0].reason_code == "OUTPUT_LIMIT"
    assert isinstance(caught.value.exceptions[1], OSError)


def test_spawn_failure_is_classified() -> None:
    with pytest.raises(CommandFailure) as caught:
        SlurmCommandRunner().run(("/no/such/slurm/binary",), guard())
    assert (
        caught.value.reason_code == "START_FAILED"
        and caught.value.capture.returncode is None
    )


@pytest.mark.parametrize("limit", [None, False, 0, -1, 1.0, "100", 8 * 1024 * 1024 + 1])
def test_invalid_output_limits(limit: object) -> None:
    with pytest.raises(ValueError):
        SlurmCommandRunner(max_output_bytes=cast(int, limit))


@pytest.mark.parametrize(
    "timeout", [None, False, 0, -1, "1", float("nan"), float("inf"), 11, 10**500]
)
def test_invalid_cleanup_deadlines(timeout: object) -> None:
    with pytest.raises(ValueError):
        SlurmCommandRunner(reap_timeout=cast(float, timeout))


@pytest.mark.parametrize(
    "argv",
    [
        None,
        [],
        (),
        ("sacct",),
        ("/bin/echo", ""),
        ("/bin/echo", "a\0b"),
        ("/bin/echo", 1),
    ],
)
def test_invalid_command_before_spawn(argv: object) -> None:
    with pytest.raises(ValueError):
        SlurmCommandRunner().run(cast(tuple[str, ...], argv), guard())
