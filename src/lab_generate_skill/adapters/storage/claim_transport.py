"""One fixed installed read worker; no parent filesystem fallback or retry."""

import os
from dataclasses import dataclass
from lab_generate_skill.domain.errors import EvidenceError, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
)
from lab_generate_skill.adapters.processes.fixed_read import run_fixed_read
from .claim_protocol import (
    ClaimReadRequest,
    CLAIM_READ_REQUEST,
    ClaimReadReply,
    encode_claim_command,
    decode_claim_reply,
    ENTRY,
    MAX_REPLY,
)


@dataclass(frozen=True)
class ClaimReadExecution:
    reply: ClaimReadReply
    capture: CommandCapture


class ClaimReadFailure(EvidenceError):
    def __init__(
        self,
        phase: str,
        capture: CommandCapture | None,
        reply: ClaimReadReply | None,
    ) -> None:
        self.phase, self.capture, self.reply = phase, capture, reply
        super().__init__("Claim read failed; retain capture and original selection")


def check_claim_controller(
    command: ClaimReadRequest, control: OperationControl
) -> None:
    control.checkpoint()
    if (
        current_process_identity() != command.scope.writer
        or os.getresuid() != (command.scope.execution.uid,) * 3
    ):
        raise OwnershipConflict("Claim read belongs to another controller/UID")
    control.checkpoint()


class ClaimReadTransport:
    def __init__(self, *, reap_timeout: float = 2.0) -> None:
        self._runner = ProcessRunner(
            max_output_bytes=MAX_REPLY, reap_timeout=reap_timeout
        )

    def execute(
        self, command: ClaimReadRequest, control: OperationControl
    ) -> ClaimReadExecution:
        command = CLAIM_READ_REQUEST.validate_python(command)
        packet = encode_claim_command(command)
        argv = (
            command.scope.config.installation.python_executable,
            "-I",
            "-B",
            "-m",
            ENTRY,
        )
        reply, capture = run_fixed_read(
            self._runner,
            argv,
            packet,
            control,
            decode_claim_reply,
            lambda: check_claim_controller(command, control),
            ClaimReadFailure,
            "claim_read",
        )
        return ClaimReadExecution(reply, capture)
