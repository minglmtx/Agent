"""Transport accepts success only after exact response and confirmed child exit."""

from dataclasses import replace
from pathlib import Path
from typing import cast
import pytest

from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    CommandFailure,
    ProcessTermination,
)
from lab_generate_skill.adapters.processes.remote_errors import RemoteError
from lab_generate_skill.adapters.storage.worker_transport import EvidenceWorkerTransport
from lab_generate_skill.adapters.storage.worker_protocol import (
    EvidenceReply,
    encode_reply,
    decode_command,
)
from lab_generate_skill.adapters.storage.exchange_result import (
    EvidenceExchangeFailure,
    WorkerReportedFailure,
    retained_exchange,
)
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from evidence_worker_fixtures import command
from test_slurm_commands import guard

ARGV = (
    "/trusted/python",
    "-I",
    "-B",
    "-m",
    "lab_generate_skill.adapters.storage.evidence_worker",
)


def complete(root: Path) -> CommandCapture:
    request = command(root)
    reply = EvidenceReply(
        exchange_id=request.exchange_id, operation="put", reference=request.reference
    )
    return CommandCapture(
        ARGV,
        0,
        encode_reply(request, reply),
        b"",
        True,
        ProcessTermination(123, "reaped", 0, False),
    )


def test_exact_entry_one_dispatch_and_control_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = guard()
    calls: list[tuple[str, ...]] = []

    def run(
        self: ProcessRunner,
        argv: tuple[str, ...],
        op: OperationControl,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        assert argv == ARGV and op is control and stdin_bytes is not None
        decoded, body = decode_command(stdin_bytes)
        assert decoded == command(tmp_path) and body == b"evidence"
        calls.append(argv)
        return complete(tmp_path)

    monkeypatch.setattr(ProcessRunner, "run", run)
    result = EvidenceWorkerTransport(ARGV[0]).execute(
        command(tmp_path), b"evidence", control
    )
    assert result.reply.error is None and result.payload == b"" and len(calls) == 1
    assert list(tmp_path.iterdir()) == []  # parent never initializes evidence root


@pytest.mark.parametrize(
    "fault",
    [
        "missing_termination",
        "unknown_exit",
        "cleanup_error",
        "nonzero",
        "stderr",
        "incomplete",
        "wrong_command",
        "bad_packet",
        "wrong_reply",
    ],
)
def test_success_requires_every_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    capture = complete(tmp_path)
    if fault == "missing_termination":
        capture = replace(capture, termination=None)
    elif fault == "unknown_exit":
        capture = replace(
            capture, termination=ProcessTermination(123, "unconfirmed", None, True)
        )
    elif fault == "cleanup_error":
        capture = replace(
            capture,
            termination=ProcessTermination(123, "reaped", 0, True, ("OSError",)),
        )
    elif fault == "nonzero":
        capture = replace(
            capture,
            returncode=7,
            termination=ProcessTermination(123, "reaped", 7, False),
        )
    elif fault == "stderr":
        capture = replace(capture, stderr=b"unexpected")
    elif fault == "incomplete":
        capture = replace(capture, complete=False)
    elif fault == "wrong_command":
        capture = replace(capture, argv=("/other/python",))
    elif fault == "bad_packet":
        capture = replace(capture, stdout=b"broken")
    else:
        other = command(tmp_path).model_copy(update={"exchange_id": "other"})
        capture = replace(
            capture,
            stdout=encode_reply(
                other,
                EvidenceReply(
                    exchange_id="other", operation="put", reference=other.reference
                ),
            ),
        )
    monkeypatch.setattr(ProcessRunner, "run", lambda *args, **kwargs: capture)
    with pytest.raises(EvidenceExchangeFailure) as caught:
        EvidenceWorkerTransport(ARGV[0]).execute(
            command(tmp_path), b"evidence", guard()
        )
    observation = caught.value.observation
    assert observation.command == command(tmp_path) and observation.capture is capture
    assert observation.isolation_required == (
        fault in {"missing_termination", "unknown_exit", "cleanup_error"}
    )
    assert caught.value.__cause__ is not None
    if fault not in {"bad_packet", "wrong_reply"}:
        assert observation.reply is not None  # valid facts retained, never success


def test_remote_error_and_original_reference_are_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = command(tmp_path)
    error = RemoteError(
        type_name="EvidenceIntegrityError", reason_code="EVIDENCE_INTEGRITY_MISMATCH"
    )
    reply = EvidenceReply(
        exchange_id=request.exchange_id,
        operation="put",
        reference=request.reference,
        error=error,
    )
    capture = replace(complete(tmp_path), stdout=encode_reply(request, reply))
    monkeypatch.setattr(ProcessRunner, "run", lambda *args, **kwargs: capture)
    with pytest.raises(EvidenceExchangeFailure) as caught:
        EvidenceWorkerTransport(ARGV[0]).execute(request, b"evidence", guard())
    cause = caught.value.__cause__
    assert isinstance(cause, WorkerReportedFailure) and cause.reply.error == error
    assert cause.reason_code == "EVIDENCE_INTEGRITY_MISMATCH"
    assert caught.value.observation.reply == reply
    assert retained_exchange(caught.value) is caught.value.observation


def test_primary_cleanup_group_retained_even_with_complete_reply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = replace(
        complete(tmp_path),
        complete=False,
        termination=ProcessTermination(
            123, "unconfirmed", None, True, ("TimeoutExpired",)
        ),
    )
    primary = CommandFailure("DEADLINE_EXCEEDED", capture)
    cleanup = TimeoutError("reap")
    group = ExceptionGroup("original", [primary, cleanup])
    calls = 0

    def fail(*args: object, **kwargs: object) -> CommandCapture:
        nonlocal calls
        calls += 1
        raise group

    monkeypatch.setattr(ProcessRunner, "run", fail)
    with pytest.raises(EvidenceExchangeFailure) as caught:
        EvidenceWorkerTransport(ARGV[0]).execute(
            command(tmp_path), b"evidence", guard()
        )
    assert calls == 1 and caught.value.__cause__ is group
    assert caught.value.observation.reply is not None
    assert caught.value.observation.isolation_required


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_stop_exception_keeps_type_and_exchange(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupt: type[BaseException]
) -> None:
    original = interrupt("stop")
    setattr(original, "command_capture", replace(complete(tmp_path), complete=False))

    def fail(*args: object, **kwargs: object) -> CommandCapture:
        raise original

    monkeypatch.setattr(ProcessRunner, "run", fail)
    with pytest.raises(interrupt) as caught:
        EvidenceWorkerTransport(ARGV[0]).execute(
            command(tmp_path), b"evidence", guard()
        )
    assert caught.value is original
    observation = retained_exchange(original)
    assert observation is not None and observation.reply is not None
    assert observation.command.reference == command(tmp_path).reference


def test_cancel_after_valid_reply_keeps_committed_fact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Control:
        stopped = False

        def checkpoint(self) -> float:
            if self.stopped:
                raise OperationStopped("CANCELLED", "original")
            return 5.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    control = Control()

    def finish(*args: object, **kwargs: object) -> CommandCapture:
        control.stopped = True
        return complete(tmp_path)

    monkeypatch.setattr(ProcessRunner, "run", finish)
    with pytest.raises(EvidenceExchangeFailure) as caught:
        EvidenceWorkerTransport(ARGV[0]).execute(
            command(tmp_path), b"evidence", control
        )
    assert caught.value.observation.phase == "completion"
    assert caught.value.observation.reply is not None
    assert isinstance(caught.value.__cause__, OperationStopped)


def test_invalid_or_stopped_input_has_no_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> CommandCapture:
        raise AssertionError("invalid request launched a child")

    monkeypatch.setattr(ProcessRunner, "run", forbidden)
    transport = EvidenceWorkerTransport(ARGV[0])
    with pytest.raises(ValueError):
        transport.execute(command(tmp_path), b"wrong", guard())
    with pytest.raises(OperationStopped):
        transport.execute(command(tmp_path), b"evidence", guard(-1))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "executable", [None, "relative", "", "/safe/../python", "/bad\0python", 1]
)
def test_bad_executable_rejected(executable: object) -> None:
    with pytest.raises(ValueError):
        EvidenceWorkerTransport(cast(str, executable))


def test_launch_unknown_cannot_claim_no_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> CommandCapture:
        raise RuntimeError("launch state unknown")

    monkeypatch.setattr(ProcessRunner, "run", fail)
    with pytest.raises(EvidenceExchangeFailure) as caught:
        EvidenceWorkerTransport(ARGV[0]).execute(
            command(tmp_path), b"evidence", guard()
        )
    assert (
        caught.value.observation.capture is None
        and caught.value.observation.isolation_required
    )
    assert retained_exchange(ValueError("none")) is None
