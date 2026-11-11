"""Original live parent's read-only delegation; never publication approval."""

import os
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.release_activation import (
    ReleaseDeployment,
    ReleaseSwitch,
)
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.processes.owner_pidfd import ended
from .publication_protocol import PublicationReadCommand


class DelegatedPublicationAccess:
    def __init__(
        self, command: PublicationReadCommand, worker: ProcessIdentity, parent_fd: int
    ) -> None:
        self._command, self._worker, self._parent_fd = command, worker, parent_fd

    def authorize_access(
        self,
        deployment: ReleaseDeployment,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        command = self._command
        if (
            deployment != command.deployment
            or operation != command.operation
            or os.getppid() != command.scope.writer.process_id
            or ended(self._parent_fd)
            or current_process_identity() != self._worker
            or os.getresuid() != (command.scope.execution.uid,) * 3
        ):
            raise OwnershipConflict(
                "Publication read lost its original controller/worker scope"
            )
        control.checkpoint()

    def authorize_switch(
        self,
        prior: ReleaseCurrentSnapshot,
        change: ReleaseSwitch,
        control: OperationControl,
    ) -> None:
        raise OwnershipConflict("Read-only delegation cannot publish")
