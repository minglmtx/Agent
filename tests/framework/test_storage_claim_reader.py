"""Public reader now uses the isolated transport; no synchronous-file fallback."""

from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock
import os
import pytest
from lab_generate_skill.adapters.storage.claim_reader import (
    StorageClaimReader,
)
from lab_generate_skill.adapters.storage import claim_transport as module
from lab_generate_skill.adapters.storage.claim_protocol import (
    decode_claim_command,
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
from claim_fixtures import UnitClaimAuthority
from claim_worker_fixtures import inputs, capture


def test_repeated_exact_reads_only_spawn_fixed_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope, record, command = inputs(tmp_path)
    calls = []

    def run(
        self: ProcessRunner,
        argv: tuple[str, ...],
        control: Any,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        assert stdin_bytes is not None
        assert decode_claim_command(stdin_bytes) == command
        calls.append(argv)
        return capture(command, record)

    monkeypatch.setattr(ProcessRunner, "run", run)
    reader = StorageClaimReader(
        Path(command.root),
        scope,
        OperationGuards(SystemClock(), CancelSwitch()),
        UnitClaimAuthority(),
    )
    assert (
        reader.read(record.binding.key, command.operation, control=Control()) == record
    )
    assert (
        reader.read(record.binding.key, command.operation, control=Control()) == record
    )
    assert len(calls) == 2 and calls[0] == calls[1]
    assert reader.last_execution is not None
    assert not hasattr(reader, "claim") and not hasattr(reader, "reconcile")
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
def test_invalid_capture_never_returns_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    scope, record, command = inputs(tmp_path)
    observed = capture(command, record)
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
    reader = StorageClaimReader(
        Path(command.root),
        scope,
        OperationGuards(SystemClock(), CancelSwitch()),
        UnitClaimAuthority(),
    )
    with pytest.raises(module.ClaimReadFailure) as caught:
        reader.read(record.binding.key, command.operation, control=Control())
    assert caught.value.capture is observed and reader.last_execution is None
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "case", ["uid", "effective_uid", "saved_uid", "writer", "owner", "run", "attempt"]
)
def test_denied_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    scope, record, command = inputs(tmp_path)
    uid = scope.execution.uid
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
            lambda: scope.writer.model_copy(update={"start_ticks": 1}),
        )
    else:
        field = {"owner": "owner_id", "run": "run_id", "attempt": "attempt_id"}[case]
        command = command.model_copy(
            update={"operation": command.operation.model_copy(update={field: "other"})}
        )
    runner = Mock()
    monkeypatch.setattr(ProcessRunner, "run", runner)
    reader = StorageClaimReader(
        Path(command.root),
        scope,
        OperationGuards(SystemClock(), CancelSwitch()),
        UnitClaimAuthority(),
    )
    with pytest.raises((ValueError, OwnershipConflict)):
        reader.read(record.binding.key, command.operation, control=Control())
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
    scope, _, _ = inputs(tmp_path)
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
        StorageClaimReader(
            roots[case],
            scope,
            OperationGuards(SystemClock(), CancelSwitch()),
            UnitClaimAuthority(),
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("delay", [9, 10, 11])
@pytest.mark.parametrize("rollback", [False, True])
def test_original_deadline_covers_complete_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delay: int, rollback: bool
) -> None:
    from datetime import timedelta
    from test_lifecycle import ManualClock

    scope, record, command = inputs(tmp_path)
    clock = ManualClock()
    operation = command.operation.model_copy(
        update={"deadline": clock.utcnow() + timedelta(seconds=10)}
    )
    command = command.model_copy(update={"operation": operation})

    def run(*args: Any, **kwargs: Any) -> CommandCapture:
        clock.elapsed += delay
        clock.wall += timedelta(days=-1) if rollback else timedelta(seconds=delay)
        return capture(command, record)

    monkeypatch.setattr(ProcessRunner, "run", run)
    reader = StorageClaimReader(
        Path(command.root),
        scope,
        OperationGuards(clock, CancelSwitch()),
        UnitClaimAuthority(),
    )
    if delay >= 10:
        with pytest.raises(module.ClaimReadFailure) as caught:
            reader.read(record.binding.key, operation, control=Control())
        assert caught.value.phase == "completion" and caught.value.capture is not None
    else:
        assert reader.read(record.binding.key, operation, control=Control()) == record


@pytest.mark.parametrize("delay", [9, 10, 11])
@pytest.mark.parametrize("rollback", [False, True])
def test_preparation_time_cannot_extend_original_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delay: int, rollback: bool
) -> None:
    from datetime import timedelta
    from test_lifecycle import ManualClock
    from lab_generate_skill.domain.errors import OperationStopped
    from lab_generate_skill.adapters.storage import claim_reader as reader_module
    from lab_generate_skill.adapters.storage.claim_protocol import (
        ClaimReadCommand,
    )

    scope, record, command = inputs(tmp_path)
    clock = ManualClock()
    operation = command.operation.model_copy(
        update={"deadline": clock.utcnow() + timedelta(seconds=10)}
    )
    command = command.model_copy(update={"operation": operation})
    reader = StorageClaimReader(
        Path(command.root),
        scope,
        OperationGuards(clock, CancelSwitch()),
        UnitClaimAuthority(),
    )

    def slow_validation(**kwargs: Any) -> ClaimReadCommand:
        clock.elapsed += delay
        clock.wall += timedelta(days=-1) if rollback else timedelta(seconds=delay)
        return ClaimReadCommand(**kwargs)

    monkeypatch.setattr(reader_module, "ClaimReadCommand", slow_validation)
    runner = Mock(return_value=capture(command, record))
    monkeypatch.setattr(ProcessRunner, "run", runner)
    if delay >= 10:
        with pytest.raises(OperationStopped, match="DEADLINE_EXCEEDED"):
            reader.read(record.binding.key, operation, control=Control())
        assert not runner.mock_calls
    else:
        assert reader.read(record.binding.key, operation, control=Control()) == record
        assert runner.call_count == 1


@pytest.mark.parametrize("case", ["scope", "source", "none", "empty", "wrong_type"])
def test_invalid_key_does_not_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    scope, record, command = inputs(tmp_path)
    key: Any = record.binding.key
    if case == "scope":
        key = key.model_copy(update={"scope_id": "other"})
    elif case == "source":
        key = key.model_copy(update={"source_task_id": "other"})
    elif case == "none":
        key = None
    elif case == "empty":
        key = {}
    else:
        key = True
    runner = Mock()
    monkeypatch.setattr(ProcessRunner, "run", runner)
    reader = StorageClaimReader(
        Path(command.root),
        scope,
        OperationGuards(SystemClock(), CancelSwitch()),
        UnitClaimAuthority(),
    )
    with pytest.raises((ValueError, OwnershipConflict)):
        reader.read(key, command.operation, control=Control())
    assert not runner.mock_calls and reader.last_execution is None


def test_business_authority_cannot_be_replaced_by_successful_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope, record, command = inputs(tmp_path)
    monkeypatch.setattr(
        ProcessRunner, "run", lambda *args, **kwargs: capture(command, record)
    )
    authority = UnitClaimAuthority()
    reader = StorageClaimReader(
        Path(command.root),
        scope,
        OperationGuards(SystemClock(), CancelSwitch()),
        authority,
    )
    assert (
        reader.read(record.binding.key, command.operation, control=Control()) == record
    )
    previous = reader.last_execution
    authority.denied = True
    with pytest.raises(OwnershipConflict) as caught:
        reader.read(record.binding.key, command.operation, control=Control())
    assert getattr(caught.value, "claim_read").reply.record == record
    assert reader.last_execution is previous and authority.read_calls == 2
