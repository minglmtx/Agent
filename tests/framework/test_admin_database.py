"""Native DB leaf contracts, fixed commands and preserved failure facts."""

from pathlib import Path
from typing import Any, Literal
import sys
import pytest
from lab_generate_skill.sites.shopping_admin.database import (
    AdminDatabase,
    database_argv,
)
from lab_generate_skill.sites.shopping_admin.database_contract import (
    AdminDatabaseLayout,
    AdminDatabaseSnapshot,
    DatabaseReply,
    DatabaseReplyError,
)
from lab_generate_skill.sites.shopping_admin.database_script import (
    DATABASE_SNAPSHOT_PHP,
)
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import CommandFailure
from lab_generate_skill.ports.lifecycle import OperationControl
from test_slurm_commands import guard


def layout(**updates: Any) -> AdminDatabaseLayout:
    values: dict[str, Any] = dict(
        instance_id="test-instance",
        node_root="/tmp/job",
        state_root="/tmp/job/state",
        image_path="/tmp/job/image.sif",
        image_sha256="a" * 64,
        apptainer="/usr/bin/apptainer",
    )
    values.update(updates)
    return AdminDatabaseLayout(**values)


class Commands:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.reply: bytes | None = None
        self.error: BaseException | None = None

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        self.calls.append(argv)
        control.checkpoint()
        if self.error:
            raise self.error
        operation: Literal["save", "restore"] = (
            "save" if argv[-1] == "save" else "restore"
        )
        return (
            self.reply
            if self.reply is not None
            else DatabaseReply(operation=operation, size_bytes=123, sha256="b" * 64)
            .model_dump_json()
            .encode()
        )


def test_save_and_persisted_snapshot_restore_use_fixed_original_resources() -> None:
    commands = Commands()
    database = AdminDatabase(layout(), commands)
    saved = database.save(guard())
    persisted = AdminDatabaseSnapshot.model_validate_json(saved.model_dump_json())
    another = AdminDatabase(layout(), commands)
    assert another.restore(persisted, guard()).sha256 == saved.sha256
    assert commands.calls[0][-1] == "save"
    assert commands.calls[1][-3:] == ("restore", "b" * 64, "123")
    assert commands.calls[0][:2] == ("/usr/bin/apptainer", "exec")
    assert "/tmp/job/state:/state" in commands.calls[0]
    assert DATABASE_SNAPSHOT_PHP in commands.calls[0]
    assert (
        "--databases" in DATABASE_SNAPSHOT_PHP
        and "--add-drop-database" in DATABASE_SNAPSHOT_PHP
    )
    assert (
        "--socket=" in DATABASE_SNAPSHOT_PHP
        and "reset-client.cnf" not in DATABASE_SNAPSHOT_PHP
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("node_root", "/"),
        ("state_root", "/tmp/job"),
        ("state_root", "/outside/state"),
        ("state_root", "/tmp/job/a/../state"),
        ("state_root", "/tmp/job/state:/else"),
        ("state_root", "/tmp/job/state,other"),
        ("state_root", "relative"),
        ("image_path", "/tmp/job/state/image.sif"),
        ("image_path", "/else/image.sif"),
        ("apptainer", "apptainer"),
        ("image_sha256", ""),
        ("instance_id", ""),
        ("state_root", None),
        ("image_path", True),
    ],
)
def test_invalid_layout_rejected_before_command(field: str, value: Any) -> None:
    with pytest.raises(ValueError):
        layout(**{field: value})


@pytest.mark.parametrize("change", ["instance_id", "image_sha256", "state_root"])
def test_other_instance_or_image_cannot_restore(change: str) -> None:
    commands = Commands()
    database = AdminDatabase(layout(), commands)
    saved = database.save(guard())
    value = {
        "instance_id": "other",
        "image_sha256": "c" * 64,
        "state_root": "/tmp/job/other",
    }[change]
    other = saved.model_copy(update={"layout": layout(**{change: value})})
    with pytest.raises(ValueError, match="original instance"):
        database.restore(other, guard())
    assert len(commands.calls) == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{}",
        b"[]",
        b"null",
        b"not-json",
        b'{"schema_version":"admin-database-reply/1","operation":"save","size_bytes":123,"sha256":"'
        + b"b" * 64
        + b'","operation":"save"}',
    ],
)
def test_bad_reply_retains_exact_bytes_without_retry(raw: bytes) -> None:
    commands = Commands()
    commands.reply = raw
    with pytest.raises(DatabaseReplyError) as raised:
        AdminDatabase(layout(), commands).save(guard())
    assert raised.value.raw_reply == raw and raised.value.__cause__ is not None
    assert len(commands.calls) == 1


@pytest.mark.parametrize(
    "field,value", [("size_bytes", 124), ("sha256", "c" * 64), ("operation", "save")]
)
def test_restore_reply_must_match_original_pin(field: str, value: Any) -> None:
    commands = Commands()
    database = AdminDatabase(layout(), commands)
    saved = database.save(guard())
    values = DatabaseReply(
        operation="restore", size_bytes=123, sha256="b" * 64
    ).model_dump()
    values[field] = value
    commands.reply = DatabaseReply.model_validate(values).model_dump_json().encode()
    with pytest.raises(DatabaseReplyError):
        database.restore(saved, guard())
    assert len(commands.calls) == 2


def test_original_command_and_cleanup_errors_propagate_without_retry() -> None:
    commands = Commands()
    error = ExceptionGroup(
        "native failed", [OSError("write failed"), RuntimeError("close failed")]
    )
    commands.error = error
    with pytest.raises(ExceptionGroup) as raised:
        AdminDatabase(layout(), commands).save(guard())
    assert raised.value is error and len(commands.calls) == 1


def test_checked_native_adapter_handles_success_nonzero_and_bounded_output() -> None:
    runner = CheckedNativeCommands(ProcessRunner(max_output_bytes=1024))
    assert runner.run((sys.executable, "-I", "-c", "print('ok')"), guard()) == b"ok\n"
    with pytest.raises(CommandFailure) as failed:
        runner.run(
            (
                sys.executable,
                "-I",
                "-c",
                "import sys;print('bad',file=sys.stderr);sys.exit(7)",
            ),
            guard(),
        )
    assert (
        failed.value.capture.returncode == 7 and failed.value.capture.stderr == b"bad\n"
    )
    assert (
        failed.value.capture.termination is not None
        and failed.value.capture.termination.state == "reaped"
    )
    with pytest.raises(CommandFailure):
        runner.run((sys.executable, "-I", "-c", "print('x'*2048)"), guard())


@pytest.mark.parametrize("value", [None, {}, [], True])
def test_invalid_snapshot_rejected_before_native_effects(value: Any) -> None:
    commands = Commands()
    with pytest.raises(ValueError):
        AdminDatabase(layout(), commands).restore(value, guard())
    assert not commands.calls


def test_cancelled_control_prevents_native_effects() -> None:
    from lab_generate_skill.domain.errors import OperationStopped

    class Stopped:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "native-db")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    commands = Commands()
    database = AdminDatabase(layout(), commands)
    baseline = AdminDatabaseSnapshot(layout=layout(), size_bytes=123, sha256="b" * 64)
    with pytest.raises(OperationStopped):
        database.save(Stopped())
    with pytest.raises(OperationStopped):
        database.restore(baseline, Stopped())
    assert not commands.calls


def test_checked_native_deadline_retains_original_capture() -> None:
    runner = CheckedNativeCommands(ProcessRunner())
    with pytest.raises(CommandFailure) as raised:
        runner.run(
            (sys.executable, "-I", "-c", "import time; time.sleep(60)"), guard(0.05)
        )
    capture = raised.value.capture
    assert capture.termination is not None and capture.termination.state == "reaped"
    assert raised.value.reason_code == "DEADLINE_EXCEEDED"
    assert raised.value.__cause__ is not None
