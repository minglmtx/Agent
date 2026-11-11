"""Fixed independent resolver launch after explicit cleanup admission.

Requires original live controller, linked cleanup and original reap provenance.
Unknown ending is allowed only to persist quarantine. Never repeats read/put.
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
    require_reaped,
    retained_capture,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from .registered_protocol import MAX_REGISTERED_PACKET
from .resolver_protocol import (
    StorageResolutionCommand,
    StorageResolutionResult,
    encode_resolution_command,
    decode_resolution_reply,
)


@dataclass(frozen=True)
class StorageResolutionExecution:
    result: StorageResolutionResult
    capture: CommandCapture


class StorageResolverFailure(EvidenceError):
    def __init__(
        self,
        phase: str,
        capture: CommandCapture | None,
        result: StorageResolutionResult | None,
    ) -> None:
        self.phase, self.capture, self.result = phase, capture, result
        super().__init__("Storage resolution unconfirmed; retain original history")


class StorageResolverTransport:
    def __init__(
        self,
        python_executable: str,
        admission: EvidenceStorageAdmission,
        *,
        reap_timeout: float = 2,
    ) -> None:
        if (
            type(python_executable) is not str
            or "\0" in python_executable
            or not PurePosixPath(python_executable).is_absolute()
            or ".." in PurePosixPath(python_executable).parts
        ):
            raise ValueError("Resolver requires trusted absolute Python")
        self._argv = (
            python_executable,
            "-I",
            "-B",
            "-m",
            "lab_generate_skill.bootstrap.evidence_resolver",
        )
        self._admission = admission
        self._runner = ProcessRunner(
            max_output_bytes=MAX_REGISTERED_PACKET, reap_timeout=reap_timeout
        )

    def execute(
        self,
        command: StorageResolutionCommand,
        payload: bytes,
        control: OperationControl,
    ) -> StorageResolutionExecution:
        command = StorageResolutionCommand.model_validate(command)
        control.checkpoint()
        packet = encode_resolution_command(command, payload)
        original = command.original
        if self._argv[0] != original.config.installation.python_executable:
            raise OwnershipConflict("Storage Python differs from frozen installation")
        if current_process_identity() != original.controller:
            raise OwnershipConflict("Resolution needs the original live controller")
        with operation_stage("metadata.resolve-admission"):
            self._admission.authorize_cleanup(
                original.binding,
                original.config,
                original.operation,
                command.cleanup,
                command.ending,
                control,
            )
        control.checkpoint()
        phase = "launch"
        capture: CommandCapture | None = None
        result: StorageResolutionResult | None = None
        try:
            with operation_stage("metadata.resolve-worker"):
                capture = self._runner.run(self._argv, control, stdin_bytes=packet)
            phase = "termination"
            end = require_reaped(capture)
            if (
                capture.complete is not True
                or type(capture.returncode) is not int
                or capture.returncode != 0
                or capture.stderr
                or capture.argv != self._argv
                or end.returncode != capture.returncode
            ):
                raise ValueError("Resolver did not complete with confirmed exit")
            phase = "protocol"
            with operation_stage("metadata.resolve-decode"):
                result = decode_resolution_reply(packet, capture.stdout)
            actual = result.reply.worker
            if actual.process_id != end.process_id or (
                actual.node_id,
                actual.boot_id,
            ) != (original.controller.node_id, original.controller.boot_id):
                raise OwnershipConflict(
                    "Resolution reply differs from original resolver child"
                )
            phase = "worker"
            if result.reply.error is not None:
                raise ValueError(
                    "Resolver reported original inspection or recording failure"
                )
            phase = "completion"
            control.checkpoint()
            return StorageResolutionExecution(result, capture)
        except BaseException as error:
            capture = retained_capture(error) or capture
            if result is None and capture is not None:
                try:
                    result = decode_resolution_reply(packet, capture.stdout)
                except Exception:
                    pass
            failure = StorageResolverFailure(phase, capture, result)
            if not isinstance(error, Exception):
                setattr(error, "storage_resolver", failure)
                raise
            raise failure from error
