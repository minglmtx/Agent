"""Real reusable child transport: byte boundaries, no replay and cleanup facts."""

import json
import os
import sys
import subprocess
from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.processes import session as module
from lab_generate_skill.adapters.processes.capture import (
    retained_capture,
    ProcessTermination,
)
from lab_generate_skill.adapters.processes.cleanup import finish_process
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from test_slurm_commands import guard
from process_session_fixtures import session


@pytest.mark.parametrize(
    "raw", [b"", b"hello", "任务".encode(), b"x" * (2 * 1024 * 1024)]
)
def test_repeated_frames_one_child_exact_bytes_and_graceful_close(raw: bytes) -> None:
    worker = session()
    worker.start(guard())
    try:
        pid = worker.exchange(b"pid", guard())
        assert worker.exchange(raw, guard()) == raw
        assert worker.exchange(raw, guard()) == raw
        assert worker.exchange(b"pid", guard()) == pid
        assert worker.capture.complete is False and worker.capture.termination is None
        assert worker.exchange(b"close", guard()) == b"closed"
        termination = worker.finish(guard())
        assert termination.process_id == int(pid) and termination.state == "reaped"
        assert termination.returncode == 0 and not termination.kill_requested
        assert worker.finish(guard()) == termination
        assert worker.abort(guard()) == termination
        assert worker.capture.complete
        with pytest.raises(OwnershipConflict):
            worker.exchange(b"new", guard())
        with pytest.raises(OwnershipConflict):
            worker.start(guard())
    finally:
        worker.abort(guard())


@pytest.mark.parametrize("bad", [-1, 0, True, 1.5, "2", 64 * 1024 * 1024 + 1])
def test_invalid_byte_budgets_have_no_spawn(bad: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        FramedProcessSession((sys.executable,), max_frame_bytes=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"argv": ()},
        {"argv": ["/bin/true"]},
        {"argv": ("relative",)},
        {"argv": ("/bin/echo", "\0")},
        {"reap_timeout": 0},
        {"reap_timeout": float("nan")},
        {"reap_timeout": float("inf")},
        {"reap_timeout": True},
        {"cuda_visible_devices": "0;echo bad"},
        {"cuda_visible_devices": 1},
    ],
)
def test_invalid_launch_rejected(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {"argv": (sys.executable,)}
    values.update(kwargs)
    with pytest.raises((ValueError, TypeError)):
        FramedProcessSession(**values)  # type: ignore[arg-type]


def test_bad_payload_and_expired_wait_do_not_damage_running_child() -> None:
    worker = session(limit=8)
    worker.start(guard())
    try:
        with pytest.raises(TypeError):
            worker.exchange("x", guard())  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            worker.exchange(b"x" * 9, guard())
        with pytest.raises(OperationStopped):
            worker.exchange(b"x", guard(-1))
        assert worker.exchange(b"valid", guard()) == b"valid"
    finally:
        worker.abort(guard())


@pytest.mark.parametrize(
    "command,kind",
    [
        (b"stall", OperationStopped),
        (b"partial", EOFError),
        (b"oversize", ValueError),
        (b"trailing", ValueError),
        (b"crash", EOFError),
        (b"flood", ValueError),
    ],
)
def test_failure_terminates_and_never_restarts(
    command: bytes, kind: type[BaseException]
) -> None:
    worker = session()
    worker.start(guard())
    with pytest.raises(kind) as caught:
        worker.exchange(command, guard(0.2 if command == b"stall" else 3))
    capture = retained_capture(caught.value)
    assert capture is not None and capture.termination is not None
    assert capture.termination.state == "reaped" and not capture.complete
    if command == b"crash":
        assert capture.stderr == b"complete error sentinel"
    if command == b"partial":
        assert capture.stdout == b"\x00\x00\x00\x05xx"
    if command == b"flood":
        assert len(capture.stderr) <= 4097
    with pytest.raises(OwnershipConflict):
        worker.exchange(b"x", guard())
    with pytest.raises(OwnershipConflict):
        worker.start(guard())
    assert worker.abort(guard()).process_id == capture.termination.process_id


def test_credentials_not_inherited_and_only_device_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit secret")
    monkeypatch.setenv("PYTHONPATH", "unit wrong")
    worker = session()
    worker.start(guard())
    try:
        value = json.loads(worker.exchange(b"environment", guard()))
        assert value == {
            "OPENROUTER_API_KEY": None,
            "PYTHONPATH": None,
            "CUDA_VISIBLE_DEVICES": "0",
        }
        assert worker.exchange(b"stderr", guard()) == b"ok"
        assert worker.exchange(b"close", guard()) == b"closed"
        worker.finish(guard())
        assert worker.capture.stderr == b"warning-before-reply\n"
    finally:
        worker.abort(guard())


def test_start_failure_and_abort_before_start_are_not_restart_permissions() -> None:
    worker = FramedProcessSession(("/nonexistent/lab-worker",))
    with pytest.raises(FileNotFoundError) as caught:
        worker.start(guard())
    capture = retained_capture(caught.value)
    assert capture is not None and capture.termination is not None
    assert capture.termination.state == "not_started"
    with pytest.raises(OwnershipConflict):
        worker.start(guard())
    fresh = session()
    assert fresh.abort(guard()).state == "not_started"
    with pytest.raises(OwnershipConflict):
        fresh.start(guard())


def test_finish_requires_exit_and_no_unsolicited_output() -> None:
    worker = session()
    worker.start(guard())
    with pytest.raises(OperationStopped) as caught:
        worker.finish(guard(0.1))
    capture = retained_capture(caught.value)
    assert capture is not None and capture.termination is not None
    assert capture.termination.state == "reaped"
    worker = session(source="import os;os.write(1,b'extra')")
    worker.start(guard())
    with pytest.raises(ValueError):
        worker.finish(guard())


def test_primary_and_cleanup_errors_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = session()
    worker.start(guard())
    original = finish_process
    cleanup = OSError("injected cleanup failure")

    def finish(
        process: subprocess.Popen[bytes], *, succeeded: bool, reap_timeout: float
    ) -> tuple[ProcessTermination, list[BaseException]]:
        termination, errors = original(
            process, succeeded=succeeded, reap_timeout=reap_timeout
        )
        return termination, [*errors, cleanup]

    monkeypatch.setattr(module, "finish_process", finish)
    with pytest.raises(BaseExceptionGroup) as caught:
        worker.exchange(b"partial", guard())
    assert isinstance(caught.value.exceptions[0], EOFError)
    assert caught.value.exceptions[1] is cleanup
    capture = retained_capture(caught.value)
    assert capture is not None and capture.termination is not None
    assert capture.termination.state == "reaped" and not capture.complete


def test_parent_process_identity_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = session()
    pid = os.getpid()
    monkeypatch.setattr(os, "getpid", lambda: pid + 1)
    with pytest.raises(OwnershipConflict):
        worker.start(guard())


def test_stdin_backpressure_has_a_deadline() -> None:
    worker = session(source="import time;time.sleep(30)")
    worker.start(guard())
    with pytest.raises(OperationStopped) as caught:
        worker.exchange(b"x" * (2 * 1024 * 1024), guard(0.1))
    capture = retained_capture(caught.value)
    assert capture is not None and capture.termination is not None
    assert capture.termination.state == "reaped"


def test_stderr_budget_is_cumulative_across_requests() -> None:
    worker = session(stderr_limit=30)
    worker.start(guard())
    try:
        assert worker.exchange(b"stderr", guard()) == b"ok"
        # stderr and stdout scheduling is independent; either this exchange or
        # finish observes overflow, but a clean session outcome is forbidden.
        with pytest.raises((ValueError, BaseExceptionGroup)):
            worker.exchange(b"stderr", guard())
            worker.exchange(b"close", guard())
            worker.finish(guard())
        assert not worker.capture.complete
        assert worker.capture.termination is not None
    finally:
        worker.abort(guard())


def test_cancel_while_waiting_does_not_abort_other_exchange(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading
    from lab_generate_skill.adapters.processes.session_io import exchange
    from lab_generate_skill.ports.lifecycle import OperationControl

    worker = session()
    worker.start(guard())
    entered = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def held(
        process: subprocess.Popen[bytes],
        packet: bytes,
        reply: bytearray,
        stderr: bytearray,
        limit: int,
        stderr_limit: int,
        control: OperationControl,
    ) -> bytes:
        entered.set()
        assert release.wait(5)
        return exchange(process, packet, reply, stderr, limit, stderr_limit, control)

    monkeypatch.setattr(module, "exchange", held)

    def caller() -> None:
        try:
            assert worker.exchange(b"first", guard(10)) == b"first"
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=caller)
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(OperationStopped):
            worker.exchange(b"second", guard(0.05))
        assert worker.capture.termination is None
    finally:
        release.set()
        thread.join(10)
        worker.abort(guard())
    assert not thread.is_alive() and not errors


def test_reaped_child_cleanup_retry_never_signals_a_reusable_pid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = session()
    worker.start(guard())
    cleanup = OSError("pipe close acknowledgement failed")

    def injected(
        process: subprocess.Popen[bytes], *, succeeded: bool, reap_timeout: float
    ) -> tuple[ProcessTermination, list[BaseException]]:
        termination, errors = finish_process(
            process, succeeded=succeeded, reap_timeout=reap_timeout
        )
        return termination, [*errors, cleanup]

    monkeypatch.setattr(module, "finish_process", injected)
    with pytest.raises(BaseExceptionGroup):
        worker.exchange(b"partial", guard())
    before = worker.capture.termination
    assert before is not None and before.state == "reaped" and before.cleanup_errors
    monkeypatch.setattr(module, "finish_process", finish_process)

    def forbid_resignal(pid: int, signal: int) -> None:
        raise AssertionError("A reaped PID may belong to another process group")

    monkeypatch.setattr(os, "killpg", forbid_resignal)
    ended = worker.abort(guard())
    assert ended.state == "reaped" and not ended.cleanup_errors
    assert ended.kill_requested == before.kill_requested
    assert not worker.capture.complete
