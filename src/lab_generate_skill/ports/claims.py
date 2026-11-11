"""Source-level ownership, shared by all candidates; no lease-based release.

The root/scope is trusted deployment configuration. Creation admission must
check real user scope, writer incarnation and existing historical claims.
verify_owner checks actual caller access, including explicit diagnostic/recovery
access; strings alone are insufficient. Neither callback performs task/model
effects or silently acquires a new claim. There is no production allow default.
"""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.claims import (
    SourceClaimBinding,
    SourceClaimKey,
    SourceClaimRecord,
    SourceClaimReceipt,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution import AttemptBinding, RunBinding
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.ports.lifecycle import OperationControl


class SourceClaims(Protocol):
    def require_source(
        self,
        reference: EvidenceRef,
        run: RunBinding,
        task: TaskBinding,
        op: OperationContext,
    ) -> SourceClaimRecord:
        """Read-only run-level check of actual CAS and original durable ownership.

        Requires the complete private task. Does not register, reconcile, issue
        execution permission or synthesize an attempt operation.
        """
        ...

    def claim(
        self, binding: SourceClaimBinding, op: OperationContext
    ) -> SourceClaimReceipt: ...
    def read(self, key: SourceClaimKey, op: OperationContext) -> SourceClaimRecord: ...
    def reconcile(
        self, key: SourceClaimKey, op: OperationContext
    ) -> SourceClaimReceipt:
        """Parent-linked cleanup only republishes an already committed record."""
        ...

    def require(
        self, reference: EvidenceRef, attempt: AttemptBinding, op: OperationContext
    ) -> SourceClaimRecord: ...


class ClaimAuthority(Protocol):
    def authorize_create(
        self, binding: SourceClaimBinding, plan: RunPlan, op: OperationContext
    ) -> None: ...
    def verify_owner(self, record: SourceClaimRecord, op: OperationContext) -> None: ...


@runtime_checkable
class SourceClaimBodyChecks(Protocol):
    def require_source_verified(
        self,
        receipt: SourceClaimReceipt,
        run: RunBinding,
        task: TaskBinding,
        op: OperationContext,
    ) -> SourceClaimRecord:
        """Consume same-call CAS proof, then read actual ledger/caller anew.

        Caller must retain its fresh original storage/proof checks. This body
        grants no execution, cross-call cache or reconciliation capability.
        """
        ...


@runtime_checkable
class AttemptClaimBodyChecks(Protocol):
    def require_verified(
        self,
        receipt: SourceClaimReceipt,
        attempt: AttemptBinding,
        op: OperationContext,
    ) -> SourceClaimRecord:
        """Same-admission immutable body; actual ledger and caller checked anew."""
        ...


class SourceClaimReader(Protocol):
    """Outer read-only port: existing immutable claim, original caller control.

    No creation, receipt publication, takeover or execution permission. Exact
    private binding and caller authority must be checked before returning.
    """

    def read(
        self, key: SourceClaimKey, op: OperationContext, *, control: OperationControl
    ) -> SourceClaimRecord: ...
