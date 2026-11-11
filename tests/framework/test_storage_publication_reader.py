"""Public reader now uses the isolated transport; no synchronous-file fallback."""

from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock
import os
import pytest
from lab_generate_skill.adapters.storage.publication_reader import (
    StoragePublicationReader,
)
from lab_generate_skill.adapters.storage import publication_transport as module
from lab_generate_skill.adapters.storage.publication_protocol import (
    decode_publication_command,
)
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import (
    ProcessTermination,
    CommandCapture,
)
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.domain.errors import OwnershipConflict
from test_run_journal import CancelSwitch
from cgroup_fixtures import Control
from publication_worker_fixtures import inputs, capture


def test_repeated_exact_reads_only_spawn_fixed_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launch, snapshot, command = inputs(tmp_path)
    calls = []

    def run(
        self: ProcessRunner,
        argv: tuple[str, ...],
        control: Any,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        assert stdin_bytes is not None
        assert decode_publication_command(stdin_bytes) == command
        calls.append(argv)
        return capture(command, snapshot)

    monkeypatch.setattr(ProcessRunner, "run", run)
    reader = StoragePublicationReader(
        Path(command.root), launch, OperationGuards(SystemClock(), CancelSwitch())
    )
    assert reader.read(command.operation, control=Control()) == snapshot
    assert reader.read(command.operation, control=Control()) == snapshot
    assert len(calls) == 2 and calls[0] == calls[1]
    assert reader.last_execution is not None
    assert not hasattr(reader, "initialize") and not hasattr(reader, "activate")
    assert not list(tmp_path.iterdir())  # nonexistent root was never touched by parent


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "unknown",
        "cleanup",
        "nonzero",
        "bool_code",
        "bool_complete",
        "stderr",
        "argv",
        "packet",
        "wrong_pid",
    ],
)
def test_invalid_capture_never_returns_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    launch, snapshot, command = inputs(tmp_path)
    observed = capture(command, snapshot)
    if fault == "missing":
        observed = replace(observed, termination=None)
    elif fault == "unknown":
        observed = replace(
            observed, termination=ProcessTermination(123, "unconfirmed", None, True)
        )
    elif fault == "cleanup":
        observed = replace(
            observed,
            termination=ProcessTermination(123, "reaped", 0, True, ("OSError",)),
        )
    elif fault == "nonzero":
        observed = replace(observed, returncode=3)
    elif fault == "bool_code":
        observed = replace(observed, returncode=True)
    elif fault == "bool_complete":
        observed = replace(observed, complete=cast(bool, 1))
    elif fault == "stderr":
        observed = replace(observed, stderr=b"unexpected")
    elif fault == "argv":
        observed = replace(observed, argv=("/wrong",))
    elif fault == "packet":
        observed = replace(observed, stdout=b"{}")
    else:
        observed = replace(
            observed, termination=ProcessTermination(123, "reaped", 0, False)
        )
    monkeypatch.setattr(ProcessRunner, "run", lambda *args, **kwargs: observed)
    reader = StoragePublicationReader(
        Path(command.root), launch, OperationGuards(SystemClock(), CancelSwitch())
    )
    with pytest.raises(module.PublicationReadFailure) as caught:
        reader.read(command.operation, control=Control())
    assert caught.value.capture is observed and reader.last_execution is None
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "case", ["uid", "effective_uid", "saved_uid", "writer", "owner", "run", "attempt"]
)
def test_denied_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    launch, _, command = inputs(tmp_path)
    uid = launch.scope.execution.uid
    if case == "uid":
        monkeypatch.setattr(os, "getresuid", lambda: (uid + 1,) * 3)
    elif case == "effective_uid":
        monkeypatch.setattr(os, "getresuid", lambda: (uid, uid + 1, uid))
    elif case == "saved_uid":
        monkeypatch.setattr(os, "getresuid", lambda: (uid, uid, uid + 1))
    elif case == "writer":
        monkeypatch.setattr(
            module,
            "current_process_identity",
            lambda: launch.scope.writer.model_copy(update={"start_ticks": 1}),
        )
    else:
        field = {"owner": "owner_id", "run": "run_id", "attempt": "attempt_id"}[case]
        command = command.model_copy(
            update={"operation": command.operation.model_copy(update={field: "other"})}
        )
    runner = Mock()
    monkeypatch.setattr(ProcessRunner, "run", runner)
    reader = StoragePublicationReader(
        Path(command.root), launch, OperationGuards(SystemClock(), CancelSwitch())
    )
    with pytest.raises((ValueError, OwnershipConflict)):
        reader.read(command.operation, control=Control())
    assert not runner.mock_calls and not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "case",
    [
        "outside",
        "workspace",
        "parent",
        "data",
        "sessions",
        "data_child",
        "string",
        "none",
    ],
)
def test_bad_roots_before_io(tmp_path: Path, case: str) -> None:
    launch, _, _ = inputs(tmp_path)
    roots: dict[str, Any] = {
        "outside": tmp_path.parent / "other",
        "workspace": tmp_path,
        "parent": tmp_path / "x" / ".." / "current",
        "data": tmp_path / "data",
        "sessions": tmp_path / "sessions",
        "data_child": tmp_path / "data" / "current",
        "string": str(tmp_path / "current"),
        "none": None,
    }
    with pytest.raises(ValueError):
        StoragePublicationReader(
            roots[case], launch, OperationGuards(SystemClock(), CancelSwitch())
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("delay", [9, 10, 11])
@pytest.mark.parametrize("rollback", [False, True])
def test_original_deadline_covers_complete_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delay: int, rollback: bool
) -> None:
    from datetime import timedelta
    from test_lifecycle import ManualClock

    launch, snapshot, command = inputs(tmp_path)
    clock = ManualClock()
    operation = command.operation.model_copy(
        update={"deadline": clock.utcnow() + timedelta(seconds=10)}
    )
    command = command.model_copy(update={"operation": operation})

    def run(*args: Any, **kwargs: Any) -> CommandCapture:
        clock.elapsed += delay
        clock.wall += timedelta(days=-1) if rollback else timedelta(seconds=delay)
        return capture(command, snapshot)

    monkeypatch.setattr(ProcessRunner, "run", run)
    reader = StoragePublicationReader(
        Path(command.root), launch, OperationGuards(clock, CancelSwitch())
    )
    if delay >= 10:
        with pytest.raises(module.PublicationReadFailure) as caught:
            reader.read(operation, control=Control())
        assert caught.value.phase == "completion" and caught.value.capture is not None
    else:
        assert reader.read(operation, control=Control()) == snapshot


@pytest.mark.parametrize("delay", [9, 10, 11])
@pytest.mark.parametrize("rollback", [False, True])
def test_preparation_time_cannot_extend_original_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delay: int, rollback: bool
) -> None:
    from datetime import timedelta
    from test_lifecycle import ManualClock
    from lab_generate_skill.domain.errors import OperationStopped
    from lab_generate_skill.adapters.storage import publication_reader as reader_module
    from lab_generate_skill.adapters.storage.publication_protocol import (
        PublicationReadCommand,
    )

    launch, snapshot, command = inputs(tmp_path)
    clock = ManualClock()
    operation = command.operation.model_copy(
        update={"deadline": clock.utcnow() + timedelta(seconds=10)}
    )
    command = command.model_copy(update={"operation": operation})
    reader = StoragePublicationReader(
        Path(command.root), launch, OperationGuards(clock, CancelSwitch())
    )

    def slow_validation(**kwargs: Any) -> PublicationReadCommand:
        clock.elapsed += delay
        clock.wall += timedelta(days=-1) if rollback else timedelta(seconds=delay)
        return PublicationReadCommand(**kwargs)

    monkeypatch.setattr(reader_module, "PublicationReadCommand", slow_validation)
    runner = Mock(return_value=capture(command, snapshot))
    monkeypatch.setattr(ProcessRunner, "run", runner)
    if delay >= 10:
        with pytest.raises(OperationStopped, match="DEADLINE_EXCEEDED"):
            reader.read(operation, control=Control())
        assert not runner.mock_calls
    else:
        assert reader.read(operation, control=Control()) == snapshot
        assert runner.call_count == 1
