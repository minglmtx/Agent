"""Selector boundaries, actual child stdin, partial failure and cancellation."""

from pathlib import Path
from typing import cast
import pytest

from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_input_commands import (
    CheckedNativeInputCommands,
)
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    CommandFailure,
    ProcessTermination,
    retained_capture,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from test_slurm_commands import cmd, guard


class ObservedRunner(ProcessRunner):
    def __init__(self, capture: CommandCapture) -> None:
        self.capture = capture
        self.calls: list[tuple[tuple[str, ...], bytes | None]] = []

    def run(
        self,
        argv: tuple[str, ...],
        control: OperationControl,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        self.calls.append((argv, stdin_bytes))
        return self.capture


def result(
    *, complete: bool = True, code: int = 0, reaped: bool = True
) -> CommandCapture:
    return CommandCapture(
        cmd("pass"),
        code,
        b"native-output",
        b"private-error",
        complete,
        ProcessTermination(
            1234, "reaped" if reaped else "unconfirmed", code if reaped else None, False
        ),
    )


@pytest.mark.parametrize("size", [1, 8192])
def test_actual_child_gets_stdin_without_selector_in_argv(size: int) -> None:
    runner = CheckedNativeInputCommands(ProcessRunner(max_output_bytes=16 * 1024))
    argv = cmd(
        "import os,sys; data=sys.stdin.buffer.read(); assert 'x'*100 not in repr(sys.argv); assert not any('KEY' in x for x in os.environ); sys.stdout.buffer.write(data)"
    )
    assert runner.run_input(argv, b"x" * size, guard()) == b"x" * size


@pytest.mark.parametrize("bad", [None, "x", bytearray(b"x"), b"", b"x" * 8193, True, 1])
def test_invalid_selector_rejected_before_process(bad: object) -> None:
    runner = ObservedRunner(result())
    with pytest.raises(ValueError, match="8 KiB"):
        CheckedNativeInputCommands(runner).run_input(
            cmd("pass"), cast(bytes, bad), guard()
        )
    assert runner.calls == []


@pytest.mark.parametrize(
    "complete,code,reaped", [(False, 0, True), (True, 7, True), (True, 0, False)]
)
def test_partial_failed_or_unreaped_result_is_not_returned(
    complete: bool, code: int, reaped: bool
) -> None:
    capture = result(complete=complete, code=code, reaped=reaped)
    runner = ObservedRunner(capture)
    with pytest.raises(CommandFailure) as error:
        CheckedNativeInputCommands(runner).run_input(cmd("pass"), b"selector", guard())
    assert retained_capture(error.value) is capture
    assert len(runner.calls) == 1


def test_actual_nonzero_keeps_partial_stdout_and_reaped_capture(tmp_path: Path) -> None:
    path = tmp_path / "original-only"
    argv = cmd(
        f"import pathlib,sys; pathlib.Path({str(path)!r}).write_bytes(sys.stdin.buffer.read()); print('partial'); sys.exit(7)"
    )
    with pytest.raises(CommandFailure) as error:
        CheckedNativeInputCommands(ProcessRunner()).run_input(
            argv, b"selected-account", guard()
        )
    assert path.read_bytes() == b"selected-account"
    assert error.value.capture.stdout == b"partial\n"
    assert error.value.capture.termination is not None
    assert error.value.capture.termination.state == "reaped"
    assert error.value.capture.returncode == 7


def test_actual_deadline_preserves_side_effect_without_retry(tmp_path: Path) -> None:
    path = tmp_path / "original-only"
    argv = cmd(
        f"import pathlib,sys,time; pathlib.Path({str(path)!r}).write_bytes(sys.stdin.buffer.read()); print('written',flush=True); time.sleep(30)"
    )
    with pytest.raises(CommandFailure) as error:
        CheckedNativeInputCommands(ProcessRunner(reap_timeout=0.5)).run_input(
            argv, b"selected-account", guard(1)
        )
    assert path.read_bytes() == b"selected-account"
    assert error.value.reason_code == "DEADLINE_EXCEEDED"
    assert not error.value.capture.complete
    assert error.value.capture.termination is not None
    assert error.value.capture.termination.state == "reaped"


@pytest.mark.parametrize(
    "exception", [RuntimeError("cancelled"), KeyboardInterrupt("stopped")]
)
def test_stop_after_success_retains_original_capture(exception: BaseException) -> None:
    class StoppedControl:
        def checkpoint(self) -> float:
            raise exception

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    capture = result()
    runner = ObservedRunner(capture)
    with pytest.raises(type(exception)) as caught:
        CheckedNativeInputCommands(runner).run_input(
            cmd("pass"), b"selector", StoppedControl()
        )
    assert caught.value is exception
    assert retained_capture(caught.value) is capture
    assert len(runner.calls) == 1


def test_repeated_read_has_no_hidden_input_or_output_cache() -> None:
    runner = ObservedRunner(result())
    commands = CheckedNativeInputCommands(runner)
    for data in [b"account-one", b"account-two"]:
        assert commands.run_input(cmd("pass"), data, guard()) == b"native-output"
    assert [data for _, data in runner.calls] == [b"account-one", b"account-two"]
