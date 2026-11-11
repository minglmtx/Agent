"""Guarded original-resource restoration using explicitly injected ports.

Verify persisted registration/plan, authority termination proof and exclusive
session before backend effects. Persist intent, inspect original identity,
restore idempotently, validate full coverage/evidence, then commit the receipt.
Session adapters own crash exclusion; provider close and run diagnostics remain
application responsibilities. Cooperative checks do not replace hard supervision.
"""

import hashlib

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    RecoveryPlan,
    ResourceOwner,
    ResourceRecord,
)
from lab_generate_skill.domain.recovery import (
    RecoveryIntent,
    RecoveryObservation,
    RecoveryReceipt,
    RecoveryResult,
    WriterTerminationReceipt,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import (
    OperationControl,
    OperationControls,
    ResourceJournal,
)
from lab_generate_skill.ports.recovery import (
    RecoveryBackend,
    RecoverySession,
    RecoverySessions,
    TerminationVerifier,
)


class GuardedRecoveryExecutor:
    """A restoration result is neither task success nor provider release."""

    def __init__(
        self,
        writer: ResourceOwner,
        journal: ResourceJournal,
        evidence: EvidenceStore,
        controls: OperationControls,
        verifier: TerminationVerifier,
        sessions: RecoverySessions,
        backend: RecoveryBackend,
    ) -> None:
        self._writer = ResourceOwner.model_validate(writer)
        self._journal = journal
        self._evidence = evidence
        self._controls = controls
        self._verifier = verifier
        self._sessions = sessions
        self._backend = backend

    def _refs(self, refs: tuple[EvidenceRef, ...], guard: OperationControl) -> None:
        for ref in dict.fromkeys(refs):
            guard.checkpoint()
            self._evidence.read(ref, control=guard)
            guard.checkpoint()

    @staticmethod
    def _phase(op: OperationContext, phase: str) -> OperationContext:
        identity = hashlib.sha256(op.operation_id.encode()).hexdigest()
        return OperationContext.model_validate(
            {
                **op.model_dump(),
                "operation_id": f"recovery-{phase}-{identity}",
                "parent_operation_id": op.operation_id,
            }
        )

    def _persist(
        self, data: bytes, schema: str, control: OperationControl
    ) -> EvidenceRef:
        return self._evidence.put(
            data,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer=self._backend.binding.component_id,
            ),
            control=control,
        )

    def _quarantine(
        self,
        receipt: RecoveryReceipt,
        record: ResourceRecord,
        op: OperationContext,
        guard: OperationControl,
        session: RecoverySession,
    ) -> None:
        if receipt.status == "quarantined" and record.state != "quarantined":
            self._checkpoint(guard, session)
            proof = self._persist(
                receipt.model_dump_json().encode(), "recovery-receipt/1", control=guard
            )
            self._checkpoint(guard, session)
            self._journal.advance(
                record.token,
                "quarantined",
                (proof,),
                record.revision,
                self._phase(op, "quarantine"),
            )

    def _result(
        self,
        result: RecoveryResult,
        token: AllocationToken,
        plan: RecoveryPlan,
        guard: OperationControl,
    ) -> None:
        if (
            result.allocation_id != token.allocation_id
            or result.actual_resource_id != token.expected_resource_id
        ):
            raise OwnershipConflict("Recovery result substituted the original resource")
        if {check.coverage for check in result.checks} != set(plan.state_coverage):
            raise OwnershipConflict(
                "Recovery result must cover exactly the frozen plan"
            )
        for check in result.checks:
            self._refs(check.evidence, guard)
            if check.error is not None:
                self._refs(check.error.evidence, guard)

    @staticmethod
    def _checkpoint(guard: OperationControl, session: RecoverySession) -> None:
        guard.checkpoint()
        session.checkpoint()

    def restore(
        self,
        allocation: AllocationToken,
        recovery: RecoveryPlan,
        termination: WriterTerminationReceipt,
        op: OperationContext,
    ) -> RecoveryReceipt:
        allocation = AllocationToken.model_validate(allocation)
        recovery = RecoveryPlan.model_validate(recovery)
        termination = WriterTerminationReceipt.model_validate(termination)
        op = OperationContext.model_validate(op)
        if (
            op.mode != "cleanup"
            or op.run_id != allocation.owner.run_id
            or op.owner_id != allocation.owner.owner_id
            or op.attempt_id != allocation.attempt_id
            or op.allocation_id != allocation.allocation_id
            or op.recovery_ref != allocation.recovery_ref
        ):
            raise OwnershipConflict("Recovery requires exact original cleanup context")
        intent = RecoveryIntent(
            allocation=allocation,
            binding=self._backend.binding,
            recovery_writer=self._writer,
            operation_id=op.operation_id,
            termination=termination,
        )
        if (
            recovery.owner != allocation.owner
            or recovery.attempt_id != allocation.attempt_id
            or intent.binding.component_id != recovery.restore_component_id
            or intent.binding.component_version != recovery.restore_component_version
        ):
            raise OwnershipConflict(
                "Recovery plan/executor does not match the allocation"
            )
        guard = self._controls.bind(op)
        guard.checkpoint()
        with self._sessions.hold(allocation, self._writer, op) as session:
            self._checkpoint(guard, session)
            record = self._journal.read(allocation, op)
            persisted = RecoveryPlan.model_validate_json(
                self._evidence.read(allocation.recovery_ref, control=guard)
            )
            if record.token != allocation or persisted != recovery:
                raise OwnershipConflict(
                    "Recovery must use the original persisted registration and plan"
                )
            self._refs(
                (
                    *termination.evidence,
                    recovery.baseline_ref,
                    *recovery.protected_state,
                ),
                guard,
            )
            self._verifier.verify(allocation, termination, op)
            self._checkpoint(guard, session)
            previous = session.read()
            if previous is not None:
                previous = RecoveryReceipt.model_validate(previous)
                if (
                    previous.intent.allocation != allocation
                    or previous.intent.binding != intent.binding
                ):
                    raise OwnershipConflict(
                        "Stored recovery receipt has another binding"
                    )
                self._refs(
                    (
                        *previous.intent.termination.evidence,
                        *previous.observation.evidence,
                    ),
                    guard,
                )
                self._verifier.verify(allocation, previous.intent.termination, op)
                self._result(previous.result, allocation, recovery, guard)
                self._checkpoint(guard, session)
                self._quarantine(previous, record, op, guard, session)
                self._checkpoint(guard, session)
                return previous
            if record.state in ("closed", "quarantined"):
                raise OwnershipConflict(
                    "Terminal allocation cannot start new recovery effects"
                )
            session.begin(intent)
            self._checkpoint(guard, session)
            if record.state != "closing":
                intent_ref = self._persist(
                    intent.model_dump_json().encode(),
                    "recovery-intent/1",
                    control=guard,
                )
                self._checkpoint(guard, session)
                record = self._journal.advance(
                    allocation,
                    "closing",
                    (intent_ref,),
                    record.revision,
                    self._phase(op, "begin"),
                )
                self._checkpoint(guard, session)
            observed = RecoveryObservation.model_validate(
                self._backend.inspect(allocation, op)
            )
            self._refs(observed.evidence, guard)
            if (
                observed.allocation_id != allocation.allocation_id
                or observed.actual_resource_id != allocation.expected_resource_id
            ):
                raise OwnershipConflict(
                    "Original resource is missing or identity differs; do not recreate"
                )
            self._checkpoint(guard, session)
            result = RecoveryResult.model_validate(
                self._backend.restore(allocation, recovery, session, op)
            )
            self._checkpoint(guard, session)
            self._result(result, allocation, recovery, guard)
            receipt = RecoveryReceipt(
                intent=intent,
                observation=observed,
                result=result,
                status=(
                    "restored"
                    if all(check.status == "restored" for check in result.checks)
                    else "quarantined"
                ),
            )
            self._checkpoint(guard, session)
            session.commit(receipt)
            self._checkpoint(guard, session)
            self._quarantine(receipt, record, op, guard, session)
            self._checkpoint(guard, session)
            return receipt
