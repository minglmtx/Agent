"""Durable one-source ownership using the existing atomic snapshot primitive.

Record first, CAS receipt second: receipt failure cannot make another owner win.
Exact claim replay only recovers the original receipt and grants no permission
to repeat external execution. No deletion, lease expiry or automatic takeover.
"""

from pathlib import Path
from pydantic import TypeAdapter
from lab_generate_skill.domain.claims import (
    ClaimCommitUnconfirmed,
    SourceClaimBinding,
    SourceClaimKey,
    SourceClaimRecord,
    SourceClaimReceipt,
    check_claim_operation,
    check_source_claim,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution import AttemptBinding, RunBinding
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.validation import Identifier
from lab_generate_skill.ports.claims import ClaimAuthority
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.adapters.plans.claim_evidence import (
    ClaimEvidence,
    MAX_CLAIM_BYTES,
)
from lab_generate_skill.adapters.storage.atomic_snapshot import (
    AtomicSnapshotFile,
    SnapshotTransaction,
)


from .claim_snapshot import decode_claim, read_claim_record


class FileSourceClaims:
    def __init__(
        self,
        root: Path,
        scope_id: str,
        controls: OperationControls,
        evidence: EvidenceStore,
        plans: RunPlans,
        authority: ClaimAuthority,
    ) -> None:
        self._root = root
        self._scope = TypeAdapter(Identifier).validate_python(scope_id, strict=True)
        self._controls, self._evidence, self._authority = (
            controls,
            ClaimEvidence(evidence, plans),
            authority,
        )

    def _file(self, key: SourceClaimKey) -> AtomicSnapshotFile:
        if key.scope_id != self._scope:
            raise OwnershipConflict(
                "Claim scope differs from trusted ledger configuration"
            )
        return AtomicSnapshotFile(self._root, key.filename, max_bytes=MAX_CLAIM_BYTES)

    def claim(
        self, binding: SourceClaimBinding, op: OperationContext
    ) -> SourceClaimReceipt:
        binding, op = SourceClaimBinding.model_validate(
            binding
        ), OperationContext.model_validate(op)
        check_claim_operation(binding, op, creating=True)
        candidate = SourceClaimRecord(binding=binding, operation=op)
        raw = candidate.model_dump_json().encode()
        if len(raw) > MAX_CLAIM_BYTES:
            raise ValueError("Claim record exceeds frozen size limit")
        file = self._file(binding.key)
        control = self._controls.bind(op)
        record = candidate
        reference: EvidenceRef | None = None
        committing = False
        try:
            with file.locked(control) as transaction:
                old = transaction.read()
                if old is not None:
                    record = decode_claim(old, binding.key)
                    if record.binding != binding:
                        raise OwnershipConflict(
                            "Source is already claimed by a different immutable binding"
                        )
                    self._authority.verify_owner(record, op)
                else:
                    plan = self._evidence.plan(binding, op)
                    self._authority.authorize_create(binding, plan, op)
                control.checkpoint()
                committing = True
                if old is None:
                    transaction.write(raw)
                reference = self._evidence.publish(record, control=control)
                receipt = SourceClaimReceipt(record=record, reference=reference)
                transaction.checkpoint()
            return receipt
        except BaseException as error:
            if committing:
                raise ClaimCommitUnconfirmed(record, reference) from error
            raise

    def read(self, key: SourceClaimKey, op: OperationContext) -> SourceClaimRecord:
        key, op = SourceClaimKey.model_validate(key), OperationContext.model_validate(
            op
        )
        control = self._controls.bind(op)
        with self._file(key).locked(control) as transaction:
            record = self._read_locked(transaction, key, op)
        return record

    def _read_locked(
        self,
        transaction: SnapshotTransaction,
        key: SourceClaimKey,
        op: OperationContext,
    ) -> SourceClaimRecord:
        record = read_claim_record(transaction, key, op)
        self._authority.verify_owner(record, op)
        transaction.checkpoint()
        return record

    def reconcile(
        self, key: SourceClaimKey, op: OperationContext
    ) -> SourceClaimReceipt:
        key, op = SourceClaimKey.model_validate(key), OperationContext.model_validate(
            op
        )
        if (
            op.mode != "cleanup"
            or op.attempt_id is not None
            or op.allocation_id is not None
            or op.recovery_ref is not None
        ):
            raise OwnershipConflict(
                "Claim reconciliation requires original run-level cleanup scope"
            )
        control = self._controls.bind(op)
        record: SourceClaimRecord | None = None
        reference: EvidenceRef | None = None
        publishing = False
        try:
            with self._file(key).locked(control) as transaction:
                record = self._read_locked(transaction, key, op)
                if op.parent_operation_id != record.operation.operation_id:
                    raise OwnershipConflict(
                        "Cleanup must refer to the original claim registration"
                    )
                publishing = True
                reference = self._evidence.publish(record, control=control)
                receipt = SourceClaimReceipt(record=record, reference=reference)
                transaction.checkpoint()
            return receipt
        except BaseException as error:
            if publishing and record is not None:
                raise ClaimCommitUnconfirmed(record, reference) from error
            raise

    def require(
        self, reference: EvidenceRef, attempt: AttemptBinding, op: OperationContext
    ) -> SourceClaimRecord:
        reference, attempt, op = (
            EvidenceRef.model_validate(reference),
            AttemptBinding.model_validate(attempt),
            OperationContext.model_validate(op),
        )
        if reference != attempt.claim_ref or op.attempt_id != attempt.attempt_id:
            raise OwnershipConflict(
                "Claim check must retain this exact attempt and reference"
            )
        control = self._controls.bind(op)
        control.checkpoint()
        record = self._evidence.load(reference, control=control)
        return self._require_attempt_record(record, reference, attempt, op)

    def require_verified(
        self,
        receipt: SourceClaimReceipt,
        attempt: AttemptBinding,
        op: OperationContext,
    ) -> SourceClaimRecord:
        receipt = SourceClaimReceipt.model_validate(receipt)
        attempt, op = AttemptBinding.model_validate(
            attempt
        ), OperationContext.model_validate(op)
        if (
            receipt.reference != attempt.claim_ref
            or op.attempt_id != attempt.attempt_id
        ):
            raise OwnershipConflict(
                "Claim body check must retain this exact attempt and reference"
            )
        if receipt.reference.size_bytes > MAX_CLAIM_BYTES:
            raise ValueError("Claim evidence exceeds its bounded record limit")
        self._controls.bind(op).checkpoint()
        return self._require_attempt_record(
            receipt.record, receipt.reference, attempt, op
        )

    def _require_attempt_record(
        self,
        record: SourceClaimRecord,
        reference: EvidenceRef,
        attempt: AttemptBinding,
        op: OperationContext,
    ) -> SourceClaimRecord:
        control = self._controls.bind(op)
        control.checkpoint()
        if (
            record.binding.run != attempt.run
            or record.binding.task.identity != attempt.task
        ):
            raise OwnershipConflict("Attempt differs from original claim run or task")
        persisted = self.read(record.binding.key, op)
        if persisted != record:
            raise EvidenceIntegrityError(
                "Claim CAS differs from original durable ownership"
            )
        control.checkpoint()
        return record

    def require_source(
        self,
        reference: EvidenceRef,
        run: RunBinding,
        task: TaskBinding,
        op: OperationContext,
    ) -> SourceClaimRecord:
        reference, run, task, op = (
            EvidenceRef.model_validate(reference),
            RunBinding.model_validate(run),
            TaskBinding.model_validate(task),
            OperationContext.model_validate(op),
        )
        if op.attempt_id is not None:
            raise OwnershipConflict("Source check requires a run-level operation")
        control = self._controls.bind(op)
        control.checkpoint()
        record = check_source_claim(
            self._evidence.load(reference, control=control), reference, run, task
        )
        persisted = self.read(record.binding.key, op)
        if persisted != record:
            raise EvidenceIntegrityError(
                "Claim CAS differs from original durable ownership"
            )
        control.checkpoint()
        return record

    def require_source_verified(
        self,
        receipt: SourceClaimReceipt,
        run: RunBinding,
        task: TaskBinding,
        op: OperationContext,
    ) -> SourceClaimRecord:
        """Same-call installed CAS body; original live ledger and caller remain.

        The source consumer brackets this with its original store admission.
        No proof or allowed decision is retained by the ledger.
        """
        receipt = SourceClaimReceipt.model_validate(receipt)
        run, task, op = (
            RunBinding.model_validate(run),
            TaskBinding.model_validate(task),
            OperationContext.model_validate(op),
        )
        if op.attempt_id is not None:
            raise OwnershipConflict("Source check requires a run-level operation")
        if receipt.reference.size_bytes > MAX_CLAIM_BYTES:
            raise ValueError("Claim evidence exceeds its bounded record limit")
        control = self._controls.bind(op)
        control.checkpoint()
        record = check_source_claim(receipt.record, receipt.reference, run, task)
        persisted = self.read(record.binding.key, op)
        if persisted != record:
            raise EvidenceIntegrityError(
                "Claim body differs from original durable ownership"
            )
        control.checkpoint()
        return record
