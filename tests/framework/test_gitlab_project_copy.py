"""Exact source query/bytes, immutable180s bound and no repeat on failures."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.project_copy import (
    GitlabProjectCopyReader,
    ProjectCopyControl,
    PROJECT_ARGV,
)
from gitlab_native_fixtures import spec
from gitlab_group_fixtures import selected_spec
from site_instance_fixtures import node_path as node_path


class Time:
    now = 0.0

    def monotonic(self) -> float:
        return self.now

    def utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class Caller:
    remaining = 1000.0
    error: BaseException | None = None

    def __init__(self, clock: Time) -> None:
        self.clock = clock

    def checkpoint(self) -> float:
        if self.error is not None:
            raise self.error
        return self.remaining

    def wait(self, seconds: float) -> None:
        self.clock.sleep(seconds)


class Commands:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.calls: list[tuple[tuple[str, ...], bytes]] = []
        self.error: BaseException | None = None

    def run_input(
        self, argv: tuple[str, ...], data: bytes, control: OperationControl
    ) -> bytes:
        control.checkpoint()
        self.calls.append((argv, data))
        if self.error is not None:
            raise self.error
        return self.raw


@pytest.mark.parametrize(
    "raw", [b"", b'1,10,"A,B",path\n', '1,10,"行\n名",path\n'.encode()]
)
def test_original_copy_bytes_once_including_complete_empty_csv(
    node_path: Path, raw: bytes
) -> None:
    clock = Time()
    caller = Caller(clock)
    commands = Commands(raw)
    reader = GitlabProjectCopyReader(spec(node_path), commands, clock)
    assert reader.capture(selected_spec(), caller) == raw and reader.captured_raw == raw
    assert len(commands.calls) == 1
    argv, data = commands.calls[0]
    assert argv[-len(PROJECT_ARGV) :] == PROJECT_ARGV and data == b"\n"
    assert "Development Team" not in " ".join(argv)


def test_native_copy_deadline_and_caller_limit_cannot_be_renewed() -> None:
    clock = Time()
    caller = Caller(clock)
    control = ProjectCopyControl(caller, clock)
    assert control.checkpoint() == 180
    clock.now = 179.5
    assert control.checkpoint() == 0.5
    clock.now = 50.0
    assert control.checkpoint() == 0.5  # rollback cannot renew observed remaining
    caller.remaining = 0.25
    assert control.checkpoint() == 0.25
    caller.remaining = 1000
    assert control.checkpoint() == 0.25
    clock.now = 180
    with pytest.raises(OperationStopped):
        control.checkpoint()


@pytest.mark.parametrize("value", [-1, True, float("nan"), float("inf"), "1", None])
def test_illegal_wait_refused_before_caller_wait(value: Any) -> None:
    clock = Time()
    control = ProjectCopyControl(Caller(clock), clock)
    with pytest.raises(ValueError):
        control.wait(value)
    assert clock.now == 0


@pytest.mark.parametrize(
    "error",
    [
        OSError("complete COPY transport failed"),
        OperationStopped("CANCELLED", "copy"),
        ExceptionGroup(
            "native and cleanup", [OSError("native"), RuntimeError("close")]
        ),
    ],
)
def test_original_failure_is_retained_and_never_reinvoked(
    node_path: Path, error: BaseException
) -> None:
    clock = Time()
    commands = Commands(b"original")
    reader = GitlabProjectCopyReader(spec(node_path), commands, clock)
    reader.capture(selected_spec(), Caller(clock))
    commands.error = error
    with pytest.raises(type(error)) as caught:
        reader.capture(selected_spec(), Caller(clock))
    assert (
        caught.value is error
        and len(commands.calls) == 2
        and reader.captured_raw is None
    )


def test_cancelled_before_capture_never_invokes_native_command(node_path: Path) -> None:
    clock = Time()
    caller = Caller(clock)
    commands = Commands(b"original")
    caller.error = OperationStopped("CANCELLED", "copy-before")
    with pytest.raises(OperationStopped):
        GitlabProjectCopyReader(spec(node_path), commands, clock).capture(
            selected_spec(), caller
        )
    assert commands.calls == []
