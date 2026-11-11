"""Original namespace/birth/revision verification for a protected readonly child.

Uses the original FileEvidenceSessions read path and stable lock. No create,
intent, outcome or resolution authorization is exposed by this delegation.
"""

import os
from lab_generate_skill.adapters.processes.owner_pidfd import ended
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.domain.evidence_read_scope import EvidenceReadScope
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl


class ReadOnlySessionAuthority:
    def __init__(
        self,
        scope: EvidenceReadScope,
        worker: ProcessIdentity,
        parent_fd: int,
        control: OperationControl,
    ) -> None:
        self.scope, self.worker, self.parent_fd, self.control = (
            scope,
            worker,
            parent_fd,
            control,
        )

    def authorize_binding(
        self, binding: EvidenceSessionBinding, op: OperationContext
    ) -> None:
        self.control.checkpoint()
        if (
            binding != self.scope.binding
            or op != self.scope.operation
            or current_process_identity() != self.worker
            or os.getppid() != self.scope.controller.process_id
            or ended(self.parent_fd)
        ):
            raise OwnershipConflict("Readonly session lost original parent/scope")
        self.control.checkpoint()

    def authorize_intent(self, *args: object, **kwargs: object) -> None:
        raise PermissionError("Readonly proof cannot begin an evidence transaction")

    def verify_outcome(self, *args: object, **kwargs: object) -> None:
        raise PermissionError("Readonly proof cannot record evidence outcomes")

    def verify_resolution(self, *args: object, **kwargs: object) -> None:
        raise PermissionError("Readonly proof cannot resolve old evidence operations")
