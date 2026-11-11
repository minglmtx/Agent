"""Verify the live delegated parent, actual worker and original physical reply.

This local verifier does not grant business permissions: the fixed transport's
mandatory admission must approve the exact run/source/config before launch.
No resolution is accepted here; a worker cannot certify its own termination.
"""

import hashlib
import os
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceWorkerInstance,
    EvidenceOperationIntent,
    EvidenceOperationOutcome,
    EvidenceSessionResolution,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.owner_pidfd import ended
from lab_generate_skill.adapters.processes.worker_identity import (
    current_evidence_worker,
)
from .registered_protocol import RegisteredStorageCommand
from .physical_exchange import PhysicalEvidenceExchange, outcome_from_reply


class DelegatedStorageAuthority:
    def __init__(
        self,
        command: RegisteredStorageCommand,
        worker: EvidenceWorkerInstance,
        parent_fd: int,
        control: OperationControl,
        physical: PhysicalEvidenceExchange | None,
    ) -> None:
        self._command, self._worker = command, worker
        self._parent_fd, self._control, self._physical = parent_fd, control, physical

    def authorize_binding(
        self, binding: EvidenceSessionBinding, op: OperationContext
    ) -> None:
        self._control.checkpoint()
        if (
            binding != self._command.binding
            or op != self._command.operation
            or os.getppid() != self._command.controller.process_id
            or ended(self._parent_fd)
            or current_evidence_worker() != self._worker
        ):
            raise OwnershipConflict(
                "Original delegated storage scope is no longer live"
            )
        self._control.checkpoint()

    def authorize_intent(
        self, binding: EvidenceSessionBinding, intent: EvidenceOperationIntent
    ) -> None:
        self.authorize_binding(binding, intent.operation)
        io, physical = self._command.io, self._physical
        if (
            self._command.action != "exchange"
            or io is None
            or physical is None
            or intent.worker != self._worker
            or intent.controller != self._command.controller
            or intent.command != io
            or intent.exchange_id != io.exchange_id
            or intent.kind != io.operation
            or intent.reference != io.reference
            or intent.command_sha256 != hashlib.sha256(physical.raw).hexdigest()
        ):
            raise OwnershipConflict("Intent is not the original physical command")

    def verify_outcome(
        self,
        binding: EvidenceSessionBinding,
        intent: EvidenceOperationIntent,
        outcome: EvidenceOperationOutcome,
        op: OperationContext,
    ) -> None:
        self.authorize_intent(binding, intent)
        physical, io = self._physical, self._command.io
        if physical is None or physical.reply is None or io is None:
            raise OwnershipConflict("No actual physical reply was captured")
        if op != intent.operation or outcome != outcome_from_reply(
            io, physical.reply, op
        ):
            raise OwnershipConflict("Outcome differs from the captured original reply")

    def verify_resolution(
        self,
        binding: EvidenceSessionBinding,
        intent: EvidenceOperationIntent,
        resolution: EvidenceSessionResolution,
    ) -> None:
        raise OwnershipConflict(
            "Live storage worker cannot resolve its own termination"
        )
