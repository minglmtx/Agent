"""Real child stdin/output backpressure; private input never enters argv/capture."""

import os
from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.adapters.processes.commands import ProcessRunner, CommandFailure
from test_slurm_commands import cmd, guard


def test_stdin_output_backpressure_and_eof_without_deadlock() -> None:
    data = b"private-input" * 30000
    capture = ProcessRunner().run(
        cmd(
            "import sys,os; os.write(1,b'x'*200000); data=sys.stdin.buffer.read(); print(len(data)); assert 'OPENROUTER_API_KEY' not in os.environ"
        ),
        guard(),
        stdin_bytes=data,
    )
    assert capture.complete and capture.returncode == 0
    assert capture.stdout == b"x" * 200000 + str(len(data)).encode() + b"\n"
    assert b"private-input" not in repr(capture).encode()


def test_empty_stdin_is_closed_and_not_devnull_ambiguity() -> None:
    capture = ProcessRunner().run(
        cmd("import sys; assert sys.stdin.buffer.read()==b''; print('closed')"),
        guard(),
        stdin_bytes=b"",
    )
    assert capture.stdout == b"closed\n"


@pytest.mark.parametrize("value", ["secret", bytearray(b"x"), False, 42, []])
def test_invalid_stdin_rejected_before_spawn(value: object) -> None:
    with pytest.raises(ValueError):
        ProcessRunner().run(
            cmd("raise RuntimeError('must not run')"),
            guard(),
            stdin_bytes=cast(bytes, value),
        )


def test_child_stalls_before_reading_stdin_is_killed_and_reaped(tmp_path: Path) -> None:
    path = tmp_path / "pid"
    with pytest.raises(CommandFailure) as error:
        ProcessRunner().run(
            cmd(
                f"import os,time,pathlib; pathlib.Path({str(path)!r}).write_text(str(os.getpid())); time.sleep(20)"
            ),
            guard(0.8),
            stdin_bytes=b"x" * 200000,
        )
    assert error.value.reason_code == "DEADLINE_EXCEEDED"
    with pytest.raises(ProcessLookupError):
        os.kill(int(path.read_text()), 0)
