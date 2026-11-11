"""Original-parent delegated cleanup with independent kernel/storage checks.

A reap is supplied only by the original transport. This authority also confirms
that exact durable writer is no longer live locally before inspecting data.
Unknown reaps never become known from PID absence alone. No signals or deletion.
"""

import os
import hashlib
from pathlib import Path
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceWorkerInstance,
    EvidenceOperationIntent,
    EvidenceOperationOutcome,
    EvidenceSessionResolution,
    EvidenceWorkerEnded,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.owner_pidfd import ended
from lab_generate_skill.adapters.processes.worker_identity import (
    current_evidence_worker,
)
from lab_generate_skill.adapters.slurm.kernel_identity import read_process_identity
from lab_generate_skill.adapters.slurm.kernel_capture import KernelReadings
from .resolver_protocol import StorageResolutionCommand
from .observed_inspection import ObservedStorageInspection
from lab_generate_skill.domain.storage_unregistered import StorageUnregisteredExchange
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot


class StorageResolverAuthority:
    def __init__(
        self,
        command: StorageResolutionCommand,
        worker: EvidenceWorkerInstance,
        parent_fd: int,
        control: OperationControl,
        inspection: ObservedStorageInspection,
    ) -> None:
        self._command, self._worker, self._parent_fd, self._control = (
            command,
            worker,
            parent_fd,
            control,
        )
        self._inspection = inspection
        self._intent: EvidenceOperationIntent | None = None
        self._end: EvidenceWorkerEnded | None = None

    def authorize_binding(
        self, binding: EvidenceSessionBinding, op: OperationContext
    ) -> None:
        self._control.checkpoint()
        if (
            binding != self._command.original.binding
            or op != self._command.cleanup
            or os.getppid() != self._command.original.controller.process_id
            or ended(self._parent_fd)
            or current_evidence_worker() != self._worker
        ):
            raise OwnershipConflict("Original resolver delegation is no longer live")
        self._control.checkpoint()

    def _original_ended(self, intent: EvidenceOperationIntent) -> None:
        self._control.checkpoint()
        if (intent.worker.node_id, intent.worker.boot_id) != (
            self._worker.node_id,
            self._worker.boot_id,
        ):
            raise OwnershipConflict(
                "Cannot resolve an original writer on another boot/node"
            )
        self._process_ended(intent.worker.process_id, intent.worker.start_ticks)

    def _process_ended(self, process_id: int, start_ticks: int | None) -> None:
        self._control.checkpoint()
        readings = KernelReadings(self._control)
        try:
            actual = read_process_identity(readings, process_id, os.getuid())
        except FileNotFoundError as error:
            # A missing status/uid_map/boot file is not proof of PID absence.
            try:
                (Path("/proc") / str(process_id)).stat()
            except FileNotFoundError:
                pass
            else:
                raise OwnershipConflict(
                    "Original process observation is incomplete"
                ) from error
        else:
            if start_ticks is None or actual.start_ticks == start_ticks:
                raise OwnershipConflict("Original storage writer still exists")
        self._control.checkpoint()

    def observe_unregistered(
        self, snapshot: EvidenceSessionSnapshot
    ) -> StorageUnregisteredExchange:
        command = self._command
        original = command.original
        self.authorize_binding(original.binding, command.cleanup)
        ending = command.ending
        if ending is None or original.io is None or original.expected_revision is None:
            raise OwnershipConflict(
                "Unregistered exchange requires the original confirmed reap"
            )
        if (ending.controller.node_id, ending.controller.boot_id) != (
            self._worker.node_id,
            self._worker.boot_id,
        ):
            raise OwnershipConflict(
                "Unregistered exchange belongs to another boot/node"
            )
        # No durable worker incarnation exists in this branch. Refuse any live
        # process at the supplied PID, including reuse; absence alone is never
        # sufficient without the original trusted transport's confirmed reap.
        self._process_ended(ending.process_id, None)
        proof = StorageUnregisteredExchange(
            exchange_id=original.io.exchange_id,
            request_sha256=ending.request_sha256,
            binding=original.binding,
            operation=command.cleanup,
            ending=ending,
            observer=self._worker,
            revision=snapshot.revision,
            snapshot_sha256=hashlib.sha256(
                snapshot.model_dump_json().encode()
            ).hexdigest(),
        )
        proof.check(
            snapshot,
            exchange_id=original.io.exchange_id,
            request_sha256=ending.request_sha256,
            binding=original.binding,
            operation=command.cleanup,
            ending=ending,
            observer=self._worker,
            expected_revision=original.expected_revision,
        )
        self.authorize_binding(original.binding, command.cleanup)
        return proof

    def prepare(
        self, intent: EvidenceOperationIntent, *, replay: bool = False
    ) -> EvidenceWorkerEnded | None:
        self.authorize_binding(self._command.original.binding, self._command.cleanup)
        proof = self._command.ending
        if (
            intent.operation != self._command.original.operation
            or intent.controller != self._command.original.controller
            or intent.command != self._command.original.io
        ):
            raise OwnershipConflict("Resolver differs from original operation")
        self._intent = intent
        if proof is None:
            self._end = None
        else:
            if proof.process_id != intent.worker.process_id:
                raise OwnershipConflict("Original reap differs from durable writer")
            if not replay:
                self._original_ended(intent)
            self._end = EvidenceWorkerEnded(
                worker=intent.worker,
                observed_at=proof.observed_at,
                returncode=proof.returncode,
                verifier_id="original-storage-controller",
                proof_sha256=proof.sha256,
            )
        return self._end

    def authorize_intent(
        self, binding: EvidenceSessionBinding, intent: EvidenceOperationIntent
    ) -> None:
        raise OwnershipConflict("Resolver cannot begin original I/O")

    def verify_outcome(
        self,
        binding: EvidenceSessionBinding,
        intent: EvidenceOperationIntent,
        outcome: EvidenceOperationOutcome,
        op: OperationContext,
    ) -> None:
        raise OwnershipConflict("Resolver cannot invent an original outcome")

    def verify_resolution(
        self,
        binding: EvidenceSessionBinding,
        intent: EvidenceOperationIntent,
        resolution: EvidenceSessionResolution,
    ) -> None:
        self.authorize_binding(binding, resolution.operation)
        if intent != self._intent or resolution.worker_end != self._end:
            raise OwnershipConflict("Resolution differs from observed original writer")
        if self._end is None:
            expected = ("unknown", "unknown", "WORKER_TERMINATION_UNCONFIRMED")
        else:
            self._original_ended(intent)
            observed = self._inspection.observation
            if self._inspection.error is not None:
                expected = ("unknown", "unknown", "STORAGE_INSPECTION_FAILED")
            elif observed is None or observed.command != self._command.original.io:
                raise OwnershipConflict("No original physical inspection was captured")
            else:
                clean = observed.temporary_state in ("absent", "not_applicable")
                expected = (
                    observed.object_state,
                    "clean" if clean else "failed",
                    "STORAGE_OBSERVED" if clean else "TEMPORARY_REMAINS_UNTOUCHED",
                )
        if (
            resolution.object_state,
            resolution.cleanup_state,
            resolution.reason_code,
        ) != expected:
            raise OwnershipConflict("Resolution differs from actual storage inspection")
