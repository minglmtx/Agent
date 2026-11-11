"""Original live parent's read-only delegation; never claim approval."""

import os
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.processes.owner_pidfd import ended
from .claim_protocol import ClaimReadRequest


class DelegatedClaimAccess:
    def __init__(
        self, command: ClaimReadRequest, worker: ProcessIdentity, parent_fd: int
    ) -> None:
        self._command, self._worker, self._parent_fd = command, worker, parent_fd

    def authorize_access(
        self,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        command = self._command
        if (
            operation != command.operation
            or os.getppid() != command.scope.writer.process_id
            or ended(self._parent_fd)
            or current_process_identity() != self._worker
            or os.getresuid() != (command.scope.execution.uid,) * 3
        ):
            raise OwnershipConflict(
                "Claim read lost its original controller/worker scope"
            )
        control.checkpoint()
