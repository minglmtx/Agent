"""New parent composition cannot turn invalid captures or stop into success."""

import hashlib
from dataclasses import replace
from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.evidence_sessions import EvidenceWorkerInstance
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
    CommandFailure,
)
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.storage.registered_protocol import (
    RegisteredStorageReply,
    encode_registered_command,
    encode_registered_reply,
)
from lab_generate_skill.adapters.storage.registered_transport import (
    RegisteredStorageTransport,
    RegisteredStorageFailure,
)
from registered_storage_fixtures import ExplicitAdmission, request
from test_slurm_commands import guard
from storage_installation_fixtures import unit_storage_sources

ARGV = (
    "/trusted/python",
    "-I",
    "-B",
    "-m",
    "lab_generate_skill.bootstrap.evidence_worker",
)


def complete(root: Path) -> tuple[CommandCapture, object]:
    cmd = request(root, create=True)
    worker = EvidenceWorkerInstance(
        node_id=cmd.controller.node_id,
        boot_id=cmd.controller.boot_id,
        process_id=123,
        start_ticks=1,
    )
    reply = RegisteredStorageReply(
        command_sha256=hashlib.sha256(encode_registered_command(cmd)).hexdigest(),
        worker=worker,
        phase="completion",
        installed_sources=unit_storage_sources(cmd.config.installation),
    )
    raw = encode_registered_reply(
        reply,
        EvidenceSessionSnapshot(binding=cmd.binding, capacity=cmd.config.capacity),
    )
    return (
        CommandCapture(
            ARGV, 0, raw, b"", True, ProcessTermination(123, "reaped", 0, False)
        ),
        cmd,
    )


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
def test_invalid_capture_never_confirms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from lab_generate_skill.adapters.storage.registered_protocol import (
        RegisteredStorageCommand,
    )

    capture, value = complete(tmp_path)
    cmd = RegisteredStorageCommand.model_validate(value)
    if fault == "missing":
        capture = replace(capture, termination=None)
    elif fault == "unknown":
        capture = replace(
            capture, termination=ProcessTermination(123, "unconfirmed", None, True)
        )
    elif fault == "cleanup":
        capture = replace(
            capture,
            termination=ProcessTermination(123, "reaped", 0, True, ("OSError",)),
        )
    elif fault == "nonzero":
        capture = replace(capture, returncode=3)
    elif fault == "bool_code":
        capture = replace(capture, returncode=False)
    elif fault == "bool_complete":
        capture = replace(capture, complete=1)  # type: ignore[arg-type]
    elif fault == "stderr":
        capture = replace(capture, stderr=b"failure")
    elif fault == "argv":
        capture = replace(capture, argv=("/other/python",))
    elif fault == "packet":
        capture = replace(capture, stdout=b"bad")
    else:
        capture = replace(
            capture, termination=ProcessTermination(124, "reaped", 0, False)
        )
    calls = []

    def run(*args: object, **kwargs: object) -> CommandCapture:
        calls.append(1)
        return capture

    monkeypatch.setattr(ProcessRunner, "run", run)
    with pytest.raises(RegisteredStorageFailure) as failed:
        RegisteredStorageTransport(ARGV[0], ExplicitAdmission(cmd)).execute(
            cmd, b"", guard(30)
        )
    assert failed.value.capture is capture and len(calls) == 1
    assert list(tmp_path.iterdir()) == []


def test_unknown_process_and_cleanup_group_preserved_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.adapters.storage.registered_protocol import (
        RegisteredStorageCommand,
    )

    capture, value = complete(tmp_path)
    cmd = RegisteredStorageCommand.model_validate(value)
    capture = replace(
        capture,
        complete=False,
        termination=ProcessTermination(
            123, "unconfirmed", None, True, ("TimeoutError",)
        ),
    )
    original = ExceptionGroup(
        "original", [CommandFailure("DEADLINE_EXCEEDED", capture), TimeoutError("reap")]
    )
    calls = []

    def fail(*args: object, **kwargs: object) -> CommandCapture:
        calls.append(1)
        raise original

    monkeypatch.setattr(ProcessRunner, "run", fail)
    with pytest.raises(RegisteredStorageFailure) as failed:
        RegisteredStorageTransport(ARGV[0], ExplicitAdmission(cmd)).execute(
            cmd, b"", guard(30)
        )
    assert failed.value.__cause__ is original and failed.value.capture is capture
    assert failed.value.result is not None and len(calls) == 1


def test_cancel_after_actual_reply_keeps_known_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.adapters.storage.registered_protocol import (
        RegisteredStorageCommand,
    )

    capture, value = complete(tmp_path)
    cmd = RegisteredStorageCommand.model_validate(value)

    class Control:
        stopped = False

        def checkpoint(self) -> float:
            if self.stopped:
                raise OperationStopped("CANCELLED", "original")
            return 30

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    control = Control()

    def done(*args: object, **kwargs: object) -> CommandCapture:
        control.stopped = True
        return capture

    monkeypatch.setattr(ProcessRunner, "run", done)
    with pytest.raises(RegisteredStorageFailure) as failed:
        RegisteredStorageTransport(ARGV[0], ExplicitAdmission(cmd)).execute(
            cmd, b"", control
        )
    assert failed.value.phase == "completion" and failed.value.result is not None
    assert isinstance(failed.value.__cause__, OperationStopped)
