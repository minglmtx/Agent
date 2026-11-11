"""Single fixed installed worker launch after mandatory storage admission.

No parent filesystem effects, session creation fallback or retries. Parent proc
identity, launch and admission can block; this is not a complete hard-I/O claim.
A returned snapshot/outcome still needs independent original-worker resolution.
"""

from lab_generate_skill.adapters.operation_progress import operation_stage
from dataclasses import dataclass
from pathlib import PurePosixPath
from lab_generate_skill.domain.errors import EvidenceError, OwnershipConflict
from lab_generate_skill.ports.evidence_storage import EvidenceStorageAdmission
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    retained_capture,
    require_reaped,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.domain.storage_termination import StorageProcessEnd
from .termination_capture import captured_storage_end
from .registered_protocol import (
    RegisteredStorageCommand,
    RegisteredWorkerResult,
    MAX_REGISTERED_PACKET,
    encode_registered_command,
    decode_registered_reply,
)


@dataclass(frozen=True)
class RegisteredStorageExecution:
    result: RegisteredWorkerResult
    capture: CommandCapture
    ending: StorageProcessEnd | None


class RegisteredStorageFailure(EvidenceError):
    def __init__(
        self,
        phase: str,
        capture: CommandCapture | None,
        result: RegisteredWorkerResult | None,
        ending: StorageProcessEnd | None,
    ) -> None:
        self.phase, self.capture, self.result = phase, capture, result
        self.ending = ending
        super().__init__(
            "Registered storage failed; retain original session, never retry"
        )


class RegisteredStorageTransport:
    def __init__(
        self,
        python_executable: str,
        admission: EvidenceStorageAdmission,
        *,
        reap_timeout: float = 2.0,
    ) -> None:
        if (
            type(python_executable) is not str
            or "\0" in python_executable
            or not PurePosixPath(python_executable).is_absolute()
            or ".." in PurePosixPath(python_executable).parts
        ):
            raise ValueError("Storage worker needs a trusted absolute Python path")
        self._argv = (
            python_executable,
            "-I",
            "-B",
            "-m",
            "lab_generate_skill.bootstrap.evidence_worker",
        )
        self._admission = admission
        self._runner = ProcessRunner(
            max_output_bytes=MAX_REGISTERED_PACKET, reap_timeout=reap_timeout
        )

    def execute(
        self,
        command: RegisteredStorageCommand,
        payload: bytes,
        control: OperationControl,
    ) -> RegisteredStorageExecution:
        command = RegisteredStorageCommand.model_validate(command)
        control.checkpoint()
        packet = encode_registered_command(command, payload)
        if self._argv[0] != command.config.installation.python_executable:
            raise OwnershipConflict("Storage Python differs from frozen installation")
        if current_process_identity() != command.controller:
            raise OwnershipConflict("Storage launch belongs to another controller")
        with operation_stage("metadata.dispatch-admission"):
            self._admission.authorize_storage(
                command.binding, command.config, command.operation, control
            )
        control.checkpoint()
        phase = "launch"
        capture: CommandCapture | None = None
        result: RegisteredWorkerResult | None = None
        try:
            with operation_stage("metadata.dispatch-worker"):
                capture = self._runner.run(self._argv, control, stdin_bytes=packet)
            phase = "termination"
            ended = require_reaped(capture)
            if (
                capture.complete is not True
                or type(capture.returncode) is not int
                or capture.returncode != 0
                or capture.stderr
                or capture.argv != self._argv
                or ended.returncode != capture.returncode
            ):
                raise ValueError("Registered storage process did not complete")
            phase = "protocol"
            with operation_stage("metadata.dispatch-decode"):
                result = decode_registered_reply(packet, capture.stdout)
            worker = result.reply.worker
            if worker.process_id != ended.process_id or (
                worker.node_id,
                worker.boot_id,
            ) != (command.controller.node_id, command.controller.boot_id):
                raise OwnershipConflict("Reply is not from the original local child")
            phase = "worker"
            if result.reply.error is not None or (
                result.reply.outcome is not None
                and result.reply.outcome.status == "failed"
            ):
                raise ValueError("Registered worker reported a failed operation")
            phase = "completion"
            control.checkpoint()
            return RegisteredStorageExecution(
                result,
                capture,
                captured_storage_end(command.controller, packet, self._argv, capture),
            )
        except BaseException as error:
            capture = retained_capture(error) or capture
            if result is None and capture is not None:
                try:
                    result = decode_registered_reply(packet, capture.stdout)
                except Exception:
                    pass
            failure = RegisteredStorageFailure(
                phase,
                capture,
                result,
                captured_storage_end(command.controller, packet, self._argv, capture),
            )
            if not isinstance(error, Exception):
                setattr(error, "registered_storage", failure)
                raise
            raise failure from error
