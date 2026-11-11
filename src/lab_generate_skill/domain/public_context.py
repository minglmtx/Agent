"""Freeze public construction input from one checked and safely reset attempt.

Pure composition only: callers must resolve actual references and verify physical
facts/permissions. This receipt is private; Generator receives only the unchanged
PublicConstructionContext. Batch closure and training admission remain separate.
"""

from typing import Literal, Self
from pydantic import model_validator
from .baseline import BaselineInputs, BaselineReceipt, assemble_baseline
from .construction_inputs import PublicConstructionContext
from .errors import InvalidTransition, OwnershipConflict
from .evidence import EvidenceRef
from .lifecycle import OperationContext
from .reset import ResetInputs, ResetReceipt, assemble_reset
from .state_scope import StateScope, private_state_ref
from .validation import Contract, Identifier


class PublicContextReceipt(Contract):
    schema_version: Literal["public-context-receipt/1"] = "public-context-receipt/1"
    scope: StateScope
    operation: OperationContext
    public_context_ref: EvidenceRef
    baseline_ref: EvidenceRef
    reset_ref: EvidenceRef
    spec_ref: EvidenceRef
    equivalence_scope: tuple[Identifier, ...]

    @model_validator(mode="after")
    def references_and_operation(self) -> Self:
        for ref, schema in (
            (self.baseline_ref, "baseline-receipt/1"),
            (self.reset_ref, "reset-receipt/1"),
            (self.spec_ref, "initial-state-spec/1"),
        ):
            private_state_ref(ref, schema)
        if (
            self.public_context_ref.visibility != "public"
            or self.public_context_ref.content_schema != "public-construction-context/1"
        ):
            raise ValueError("Context receipt requires its exact public projection")
        if not self.equivalence_scope or len(set(self.equivalence_scope)) != len(
            self.equivalence_scope
        ):
            raise ValueError("Context equivalence coverage must be nonempty and unique")
        op = self.operation
        if (
            (op.run_id, op.owner_id, op.attempt_id, op.mode)
            != (self.scope.owner.run_id, self.scope.owner.owner_id, None, "execute")
            or op.allocation_id is not None
            or op.recovery_ref is not None
        ):
            raise OwnershipConflict("Context freezing requires its run-level operation")
        return self


class PublicContextInputs(Contract):
    context: PublicConstructionContext
    context_ref: EvidenceRef
    baseline_inputs: BaselineInputs
    baseline: BaselineReceipt
    baseline_ref: EvidenceRef
    reset_inputs: ResetInputs
    reset: ResetReceipt
    reset_ref: EvidenceRef

    @property
    def operation_ids(self) -> frozenset[str]:
        """Original source operations; later stages cannot reuse their identities."""
        source, restoration = self.baseline_inputs, self.reset_inputs
        return (
            frozenset(
                fact.operation.operation_id
                for fact in (
                    source.environment,
                    source.preparation,
                    source.initial,
                    self.baseline,
                    restoration.task,
                    restoration.environment,
                    restoration.health,
                    self.reset,
                )
            )
            | frozenset(c.operation_id for c in restoration.closures)
            | {restoration.plan.parent_operation_id}
        )


class ContextCommitUnconfirmed(RuntimeError):
    """Known immutable qualification reference; reconcile without physical actions."""

    reason_code = "CONTEXT_COMMIT_UNCONFIRMED"

    def __init__(self, reference: EvidenceRef) -> None:
        self.reference = reference
        super().__init__("Context facts persisted; reconcile the original receipt")


def assemble_public_context(
    inputs: PublicContextInputs, operation: OperationContext
) -> PublicContextReceipt:
    inputs = PublicContextInputs.model_validate(inputs)
    operation = OperationContext.model_validate(operation)
    baseline, reset = inputs.baseline, inputs.reset
    source, restoration = inputs.baseline_inputs, inputs.reset_inputs
    if (
        assemble_baseline(source, baseline.operation) != baseline
        or assemble_reset(restoration, reset.operation) != reset
    ):
        raise OwnershipConflict("Context summaries differ from their original facts")
    if baseline.scope != reset.scope or baseline.spec_ref != restoration.plan.spec_ref:
        raise OwnershipConflict(
            "Context must close and reset its original source attempt"
        )
    if (
        restoration.plan.task_recovery_ref,
        restoration.plan.environment_recovery_ref,
    ) != (source.prepared.recovery_ref, source.environment.allocation.recovery_ref):
        raise OwnershipConflict("Context reset must restore the original task and site")
    context = inputs.context
    if (context.context_id, context.task, context.initial_observation_ref) != (
        baseline.scope.context_id,
        source.public_task,
        baseline.observation_ref,
    ):
        raise OwnershipConflict(
            "Public projection must preserve the authoritative initial view"
        )
    if operation.operation_id in inputs.operation_ids:
        raise OwnershipConflict("Context freezing cannot reuse a state operation")
    if baseline.status != "ready" or reset.status != "safe":
        raise InvalidTransition("Only a ready and safely reset source can be frozen")
    return PublicContextReceipt(
        scope=baseline.scope,
        operation=operation,
        public_context_ref=inputs.context_ref,
        baseline_ref=inputs.baseline_ref,
        reset_ref=inputs.reset_ref,
        spec_ref=baseline.spec_ref,
        equivalence_scope=baseline.equivalence_scope,
    )
