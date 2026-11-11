"""One supervised evidence exchange through a fixed installed module entry.

The executable must be release-verified by bootstrap; no PYTHONPATH, shell or
caller-selected module. This transport has no filesystem or durable admission
side effects in the parent. Its owner must persist admission before calling it
and persist isolation on unknown termination. It is not an EvidenceStore port.

Popen itself and a blocked cancellation provider still need external supervision;
this class does not claim those hard deadlines or supervisor-death containment.
"""

from pathlib import PurePosixPath

from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    require_reaped,
    retained_capture,
)
from lab_generate_skill.domain.evidence_io import EvidenceCommand
from .worker_protocol import (
    MAX_PACKET_BYTES,
    EvidenceReply,
    encode_command,
    decode_reply,
)
from .exchange_result import (
    ExchangePhase,
    ExchangeObservation,
    EvidenceExchangeResult,
    EvidenceExchangeFailure,
    WorkerReportedFailure,
)


class EvidenceWorkerTransport:
    def __init__(self, python_executable: str, *, reap_timeout: float = 2.0) -> None:
        if (
            type(python_executable) is not str
            or not python_executable
            or "\0" in python_executable
            or not PurePosixPath(python_executable).is_absolute()
            or ".." in PurePosixPath(python_executable).parts
        ):
            raise ValueError(
                "Evidence worker needs an absolute trusted Python executable"
            )
        self._argv = (
            python_executable,
            "-I",
            "-B",
            "-m",
            "lab_generate_skill.adapters.storage.evidence_worker",
        )
        self._runner = ProcessRunner(
            max_output_bytes=MAX_PACKET_BYTES, reap_timeout=reap_timeout
        )

    def execute(
        self, command: EvidenceCommand, payload: bytes, control: OperationControl
    ) -> EvidenceExchangeResult:
        command = EvidenceCommand.model_validate(command)
        control.checkpoint()
        packet = encode_command(command, payload)
        control.checkpoint()  # no child starts after validation consumes the deadline
        phase: ExchangePhase = "launch"
        capture: CommandCapture | None = None
        reply: EvidenceReply | None = None
        try:
            capture = self._runner.run(self._argv, control, stdin_bytes=packet)
            phase = "termination"
            ended = require_reaped(capture)
            phase = "process"
            if (
                capture.complete is not True
                or type(capture.returncode) is not int
                or capture.returncode != 0
                or capture.stderr
                or capture.argv != self._argv
                or ended.returncode != capture.returncode
            ):
                raise ValueError("Evidence worker did not complete successfully")
            phase = "protocol"
            reply, body = decode_reply(command, capture.stdout)
            phase = "worker"
            if reply.error is not None:
                raise WorkerReportedFailure(reply)
            phase = "completion"
            control.checkpoint()
            return EvidenceExchangeResult(reply, body, capture)
        except BaseException as error:
            capture = retained_capture(error) or capture
            if (
                phase == "launch"
                and capture is not None
                and capture.termination is not None
                and capture.termination.state != "not_started"
            ):
                phase = "transport"
            if capture is not None and reply is None:
                try:
                    reply, _ = decode_reply(command, capture.stdout)
                except Exception:
                    pass  # original capture/error remains; no fabricated response
            observation = ExchangeObservation(command, phase, capture, reply)
            if not isinstance(error, Exception):
                # Preserve interrupts and BaseExceptionGroups as stop signals.
                setattr(error, "evidence_exchange", observation)
                raise
            raise EvidenceExchangeFailure(observation) from error
