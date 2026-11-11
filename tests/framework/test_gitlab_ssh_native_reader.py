"""Selected reader input/output/binding failures before any costly native site."""

import json
from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.sites.gitlab.ssh_native_reader import (
    GitlabSshNativeReader,
    CAPTURE,
)
from gitlab_native_fixtures import spec
from gitlab_ssh_state_fixtures import native_state, selected_spec
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


class Commands:
    def __init__(self) -> None:
        self.raw = native_state().model_dump_json().encode()
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


def test_complete_capture_once_uses_fixed_program_and_private_stdin(
    node_path: Path,
) -> None:
    commands = Commands()
    reader = GitlabSshNativeReader(spec(node_path), commands)
    original = native_state()
    assert (
        reader.capture(selected_spec(), original.account.username, guard()) == original
    )
    assert reader.captured_raw == commands.raw
    assert len(commands.calls) == 1
    argv, data = commands.calls[0]
    assert argv[-2:] == ("-e", CAPTURE)
    assert original.account.username not in " ".join(argv)
    assert json.loads(data) == dict(
        task=original.task.model_dump(mode="json"), username=original.account.username
    )
    assert b"public_key" not in data and b"password" not in data
    assert (
        reader.capture(selected_spec(), original.account.username, guard()) == original
    )
    assert len(commands.calls) == 2  # explicit reads, never cached/retried internally


@pytest.mark.parametrize(
    "value",
    [
        None,
        1,
        True,
        [],
        {},
        "",
        "x" * 256,
        "bad\nname",
        "name' OR true",
        "a/b",
        "用户名",
    ],
)
def test_bad_username_fails_before_native_effects(
    node_path: Path, value: object
) -> None:
    commands = Commands()
    with pytest.raises(ValueError, match="username"):
        GitlabSshNativeReader(spec(node_path), commands).capture(
            selected_spec(), cast(str, value), guard()
        )
    assert commands.calls == []


@pytest.mark.parametrize(
    "failure",
    [
        "missing_guard",
        "wrong_task",
        "wrong_account",
        "incomplete",
        "duplicate",
        "nonfinite",
        "malformed",
        "empty",
    ],
)
def test_capture_rejects_partial_foreign_or_malformed_facts_and_retains_raw(
    node_path: Path, failure: str
) -> None:
    commands = Commands()
    data = native_state().model_dump(mode="json")
    if failure == "missing_guard":
        data["guard"].pop("projects")
    elif failure == "wrong_task":
        data["task"]["source_task_id"] = "foreign"
    elif failure == "wrong_account":
        data["account"]["username"] = "foreign"
        data["users"]["rows"][0]["username"] = "foreign"
    elif failure == "incomplete":
        data["users"]["complete"] = False
    commands.raw = json.dumps(data).encode()
    if failure == "duplicate":
        commands.raw = b'{"task":null,' + commands.raw[1:]
    elif failure == "nonfinite":
        commands.raw = commands.raw.replace(
            b'"sign_in_count": 0', b'"sign_in_count": NaN'
        )
    elif failure == "malformed":
        commands.raw = b'{"task":'
    elif failure == "empty":
        commands.raw = b""
    reader = GitlabSshNativeReader(spec(node_path), commands)
    with pytest.raises(ValueError):
        reader.capture(selected_spec(), "native-user", guard())
    assert len(commands.calls) == 1
    assert reader.captured_raw == (None if failure == "empty" else commands.raw)


@pytest.mark.parametrize(
    "error",
    [
        OSError("native read failed"),
        OperationStopped("CANCELLED", "read"),
        ExceptionGroup(
            "primary and cleanup", [OSError("primary"), RuntimeError("cleanup")]
        ),
    ],
)
def test_original_transport_failure_kept_without_reinvocation(
    node_path: Path, error: BaseException
) -> None:
    commands = Commands()
    commands.error = error
    reader = GitlabSshNativeReader(spec(node_path), commands)
    with pytest.raises(type(error)) as caught:
        reader.capture(selected_spec(), "native-user", guard())
    assert (
        caught.value is error
        and len(commands.calls) == 1
        and reader.captured_raw is None
    )


def test_failed_new_read_cannot_reuse_previous_native_bytes(node_path: Path) -> None:
    commands = Commands()
    reader = GitlabSshNativeReader(spec(node_path), commands)
    assert reader.capture(selected_spec(), "native-user", guard()) == native_state()
    assert reader.captured_raw == commands.raw
    error = OperationStopped("CANCELLED", "second-read")
    commands.error = error
    with pytest.raises(OperationStopped) as caught:
        reader.capture(selected_spec(), "native-user", guard())
    assert caught.value is error and reader.captured_raw is None
    assert len(commands.calls) == 2


def test_stop_after_known_native_return_keeps_only_this_read_bytes(
    node_path: Path,
) -> None:
    class StopAfterReturn:
        calls = 0

        def checkpoint(self) -> float:
            self.calls += 1
            if self.calls == 3:
                raise OperationStopped("CANCELLED", "known-return")
            return 10.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    commands = Commands()
    reader = GitlabSshNativeReader(spec(node_path), commands)
    with pytest.raises(OperationStopped):
        reader.capture(selected_spec(), "native-user", StopAfterReturn())
    assert reader.captured_raw == commands.raw and len(commands.calls) == 1
