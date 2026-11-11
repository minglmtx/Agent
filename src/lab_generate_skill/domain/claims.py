"""Immutable source ownership; neither a send permit nor recovery takeover.

One source key covers all candidate attempts in its trusted scope. Mutable run,
job, local task alias and release identities are deliberately absent from the
storage key; the complete original binding is retained in the claim instead.
"""

import hashlib
from typing import Literal, Self
from pydantic import model_validator
from .errors import OwnershipConflict
from .evidence import EvidenceRef
from .execution import RunBinding
from .lifecycle import OperationContext
from .state_scope import private_state_ref
from .task import TaskBinding
from .validation import Contract, Identifier


class SourceClaimKey(Contract):
    schema_version: Literal["source-claim-key/1"] = "source-claim-key/1"
    scope_id: Identifier
    source_task_id: Identifier

    @property
    def filename(self) -> str:
        # root is already the trusted scope. A changed scope ID cannot bypass
        # an existing source record inside that same directory.
        return hashlib.sha256(self.source_task_id.encode()).hexdigest() + ".claim.json"


class SourceClaimBinding(Contract):
    schema_version: Literal["source-claim-binding/1"] = "source-claim-binding/1"
    scope_id: Identifier
    run: RunBinding
    task: TaskBinding

    @property
    def key(self) -> SourceClaimKey:
        return SourceClaimKey(
            scope_id=self.scope_id, source_task_id=self.task.identity.source_task_id
        )

    @model_validator(mode="after")
    def private_plan(self) -> Self:
        private_state_ref(self.run.plan_ref, "run-plan/3")
        private_state_ref(self.run.release_ref, "release-manifest/1")
        return self


class SourceClaimRecord(Contract):
    schema_version: Literal["source-claim/1"] = "source-claim/1"
    binding: SourceClaimBinding
    operation: OperationContext

    @model_validator(mode="after")
    def original_registration(self) -> Self:
        check_claim_operation(self.binding, self.operation, creating=True)
        return self


def check_claim_operation(
    binding: SourceClaimBinding, op: OperationContext, *, creating: bool
) -> None:
    if (op.run_id, op.owner_id) != (
        binding.run.owner.run_id,
        binding.run.owner.owner_id,
    ):
        raise OwnershipConflict("Claim operation must retain original run/owner")
    if creating and (
        op.mode != "execute"
        or op.attempt_id is not None
        or op.allocation_id is not None
        or op.recovery_ref is not None
    ):
        raise OwnershipConflict(
            "Claim registration needs a run-level execute operation"
        )


class SourceClaimReceipt(Contract):
    schema_version: Literal["source-claim-receipt/1"] = "source-claim-receipt/1"
    record: SourceClaimRecord
    reference: EvidenceRef

    @model_validator(mode="after")
    def exact_record(self) -> Self:
        private_state_ref(self.reference, "source-claim/1")
        raw = self.record.model_dump_json().encode()
        if self.reference.sha256 != hashlib.sha256(
            raw
        ).hexdigest() or self.reference.size_bytes != len(raw):
            raise ValueError("Claim receipt must identify the exact original record")
        return self


class ClaimCommitUnconfirmed(RuntimeError):
    """Snapshot may be committed; inspect this original key, never change owner."""

    def __init__(
        self, record: SourceClaimRecord, reference: EvidenceRef | None
    ) -> None:
        self.record, self.reference = record, reference
        super().__init__("Original source claim commit requires reconciliation")


def check_source_claim(
    record: SourceClaimRecord,
    reference: EvidenceRef,
    run: RunBinding,
    task: TaskBinding,
) -> SourceClaimRecord:
    """Consumer-side exact receipt/binding check, not durable ownership authority.

    Call only after SourceClaims has verified the original ledger and caller.
    Full private task equality matters even when public task identities match.
    """
    receipt = SourceClaimReceipt(record=record, reference=reference)
    run, task = RunBinding.model_validate(run), TaskBinding.model_validate(task)
    if receipt.record.binding.run != run or receipt.record.binding.task != task:
        raise OwnershipConflict("Source claim differs from the complete run or task")
    return receipt.record
