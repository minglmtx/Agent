"""Mandatory live admission for one explicit corrected-stage successor.

The old claim is provenance, never a takeover or replay grant. The concrete
authority must verify the trusted authorization, parent terminal/no-business
and no-unknown outcomes, closure/Reset evidence, and real current caller/plan.
"""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.claims import SourceClaimBinding, SourceClaimRecord
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan


@runtime_checkable
class StageValidationParentChecks(Protocol):
    def verify_parent(
        self, validation: SourceStageValidation, operation: OperationContext
    ) -> None:
        """Read-only actual parent/authorization/closure check on every gate.

        Reject valid business failures being retried, pending/unknown effects,
        missing closure/Reset, stale or unrelated authorization and revocation.
        This method alone never authorizes the new owner or side effects.
        """
        ...


@runtime_checkable
class SourceStageValidationAuthority(StageValidationParentChecks, Protocol):
    def authorize_current(
        self,
        validation: SourceStageValidation,
        binding: SourceClaimBinding,
        plan: RunPlan,
        operation: OperationContext,
    ) -> None:
        """Actual new caller, original task, selected delta and current source.

        Keep all ordinary source/plan/Slurm/resource admission checks. Neither
        passed software, this descriptor nor a terminal parent grants access.
        """
        ...

    def verify_current(
        self,
        validation: SourceStageValidation,
        record: SourceClaimRecord,
        operation: OperationContext,
    ) -> None:
        """Recheck the real current caller and existing durable validation.

        Includes every source/body/reconciliation consumer; never caches an
        allow decision or repeats a model/browser operation.
        """
        ...


@runtime_checkable
class StageValidationClaimBinding(Protocol):
    @property
    def validation(self) -> SourceStageValidation:
        """Exact descriptor configured on the durable validation ledger."""
        ...
