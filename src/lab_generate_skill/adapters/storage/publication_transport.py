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
from .publication_protocol import (
    PublicationReadCommand,
    PublicationReadReply,
    encode_publication_command,
    decode_publication_reply,
    ENTRY,
    MAX_REPLY,
)


@dataclass(frozen=True)
class PublicationReadExecution:
    reply: PublicationReadReply
    capture: CommandCapture


class PublicationReadFailure(EvidenceError):
    def __init__(
        self,
        phase: str,
        capture: CommandCapture | None,
        reply: PublicationReadReply | None,
    ) -> None:
        self.phase, self.capture, self.reply = phase, capture, reply
        super().__init__(
            "Publication read failed; retain capture and original selection"
        )


def check_publication_controller(
    command: PublicationReadCommand, control: OperationControl
) -> None:
    control.checkpoint()
    if (
        current_process_identity() != command.scope.writer
        or os.getresuid() != (command.scope.execution.uid,) * 3
    ):
        raise OwnershipConflict("Publication read belongs to another controller/UID")
    control.checkpoint()


class PublicationReadTransport:
    def __init__(self, *, reap_timeout: float = 2.0) -> None:
        self._runner = ProcessRunner(
            max_output_bytes=MAX_REPLY, reap_timeout=reap_timeout
        )

    def execute(
        self, command: PublicationReadCommand, control: OperationControl
    ) -> PublicationReadExecution:
        command = PublicationReadCommand.model_validate(command)
        packet = encode_publication_command(command)
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
            decode_publication_reply,
            lambda: check_publication_controller(command, control),
            PublicationReadFailure,
            "publication_read",
        )
        return PublicationReadExecution(reply, capture)
