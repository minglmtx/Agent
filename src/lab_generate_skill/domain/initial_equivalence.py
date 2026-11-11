"""Candidate initial-state comparison against an immutable source context.

Observations and measurements may differ under the declared equivalence policy.
Missing checks stay unknown. This is a pre-Actor gate, not a candidate reset or
training gate; actual comparison evidence and physical facts require authority.
"""

from typing import Any, Literal, Self
from pydantic import model_validator, model_serializer, SerializerFunctionWrapHandler
from .baseline import BaselineInputs, BaselineReceipt, assemble_baseline
from .errors import OwnershipConflict
from .evidence import EvidenceRef
from .lifecycle import OperationContext
from .public_context import (
    PublicContextInputs,
    PublicContextReceipt,
    assemble_public_context,
)
from .state_checks import StateChecks
from .state_scope import StateFact, private_state_ref
from .validation import Contract
from .initial_adoption import InitialAdoptionBinding, InitialAdoptionInputs


def private_equivalence_ref(reference: EvidenceRef) -> None:
    if reference.content_schema not in (
        "equivalence-receipt/1",
        "equivalence-receipt/2",
    ):
        raise ValueError("Expected an explicitly selected equivalence receipt version")
    private_state_ref(reference, reference.content_schema)


class EquivalenceChecks(StateFact):
    schema_version: Literal["equivalence-checks/1", "equivalence-checks/2"] = (
        "equivalence-checks/1"
    )
    source_context_receipt_ref: EvidenceRef
    candidate_baseline_ref: EvidenceRef
    checks: StateChecks
    adoption: InitialAdoptionBinding | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.schema_version == "equivalence-checks/1":
            data.pop("adoption", None)
        return data

    @model_validator(mode="after")
    def references(self) -> Self:
        private_state_ref(self.source_context_receipt_ref, "public-context-receipt/1")
        private_state_ref(self.candidate_baseline_ref, "baseline-receipt/1")
        if self.schema_version == "equivalence-checks/1":
            if "adoption" in self.model_fields_set:
                raise ValueError("Ordinary comparison forbids an adoption field")
        elif self.adoption is None or (
            self.adoption.scope != self.scope
            or self.adoption.source_context_ref != self.source_context_receipt_ref
        ):
            raise OwnershipConflict("Comparison2 requires its exact current adoption")
        return self


class EquivalenceReceipt(StateFact):
    schema_version: Literal["equivalence-receipt/1", "equivalence-receipt/2"] = (
        "equivalence-receipt/1"
    )
    source_context_receipt_ref: EvidenceRef
    candidate_baseline_ref: EvidenceRef
    checks_ref: EvidenceRef
    status: Literal["equivalent", "rejected", "unknown"]
    adoption: InitialAdoptionBinding | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.schema_version == "equivalence-receipt/1":
            data.pop("adoption", None)
        return data

    @model_validator(mode="after")
    def references(self) -> Self:
        private_state_ref(self.source_context_receipt_ref, "public-context-receipt/1")
        private_state_ref(self.candidate_baseline_ref, "baseline-receipt/1")
        if self.schema_version == "equivalence-receipt/1":
            private_state_ref(self.checks_ref, "equivalence-checks/1")
            if "adoption" in self.model_fields_set:
                raise ValueError("Ordinary receipt forbids an adoption field")
        else:
            private_state_ref(self.checks_ref, "equivalence-checks/2")
            if self.adoption is None or (
                self.adoption.scope != self.scope
                or self.adoption.source_context_ref != self.source_context_receipt_ref
            ):
                raise OwnershipConflict("Receipt2 requires its exact current adoption")
        return self


class EquivalenceInputs(Contract):
    source_inputs: PublicContextInputs
    source: PublicContextReceipt
    source_ref: EvidenceRef
    candidate_inputs: BaselineInputs
    candidate: BaselineReceipt
    candidate_ref: EvidenceRef
    checks: EquivalenceChecks
    checks_ref: EvidenceRef
    adoption: InitialAdoptionInputs | None = None

    @model_validator(mode="after")
    def selected_checks_reference(self) -> Self:
        private_state_ref(self.checks_ref, self.checks.schema_version)
        return self

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.adoption is None:
            data.pop("adoption", None)
        return data


def assemble_equivalence(
    inputs: EquivalenceInputs, operation: OperationContext
) -> EquivalenceReceipt:
    inputs = EquivalenceInputs.model_validate(inputs)
    operation = OperationContext.model_validate(operation)
    source, candidate, facts = inputs.source, inputs.candidate, inputs.checks
    if assemble_public_context(inputs.source_inputs, source.operation) != source:
        raise OwnershipConflict("Equivalence source differs from frozen context facts")
    if assemble_baseline(inputs.candidate_inputs, candidate.operation) != candidate:
        raise OwnershipConflict("Candidate baseline differs from actual input facts")
    if facts.schema_version == "equivalence-checks/1":
        if inputs.adoption is not None:
            raise OwnershipConflict("Ordinary comparison cannot use a frozen adoption")
        if (candidate.scope.owner.run_id, candidate.scope.owner.owner_id) != (
            source.scope.owner.run_id,
            source.scope.owner.owner_id,
        ):
            raise OwnershipConflict(
                "Candidate must preserve source task/spec/run/owner in a new attempt"
            )
    else:
        if inputs.adoption is None or inputs.adoption.binding != facts.adoption:
            raise OwnershipConflict("Comparison2 lacks its complete selected adoption")
        inputs.adoption.require_source(inputs.source_ref, source, inputs.source_inputs)
        inputs.adoption.require_candidate(inputs.candidate_inputs)
    if (
        candidate.scope.task != source.scope.task
        or candidate.scope.attempt_id == source.scope.attempt_id
        or candidate.spec_ref != source.spec_ref
        or inputs.candidate_inputs.public_task != inputs.source_inputs.context.task
    ):
        raise OwnershipConflict(
            "Candidate must preserve source task/spec/run/owner in a new attempt"
        )
    if facts.scope != candidate.scope or (
        facts.source_context_receipt_ref,
        facts.candidate_baseline_ref,
    ) != (inputs.source_ref, inputs.candidate_ref):
        raise OwnershipConflict(
            "Comparison facts belong to a different source or candidate"
        )
    if (
        facts.checks.required != source.equivalence_scope
        or candidate.equivalence_scope != source.equivalence_scope
    ):
        raise OwnershipConflict("Comparison cannot reduce frozen equivalence coverage")
    stages = (
        inputs.candidate_inputs.environment.operation,
        inputs.candidate_inputs.preparation.operation,
        inputs.candidate_inputs.initial.operation,
        candidate.operation,
        facts.operation,
        operation,
    )
    if len({op.operation_id for op in stages}) != len(stages):
        raise OwnershipConflict(
            "Comparison requires distinct candidate stage operations"
        )
    if {op.operation_id for op in stages} & (
        inputs.source_inputs.operation_ids | {source.operation.operation_id}
    ):
        raise OwnershipConflict(
            "Candidate operations cannot reuse frozen source identities"
        )
    status: Literal["equivalent", "rejected", "unknown"] = "equivalent"
    if candidate.status == "unknown" or facts.checks.status == "unknown":
        status = "unknown"
    elif candidate.status == "rejected" or facts.checks.status == "fail":
        status = "rejected"
    fields: dict[str, Any] = {}
    if inputs.adoption is not None:
        fields.update(
            schema_version="equivalence-receipt/2", adoption=inputs.adoption.binding
        )
    return EquivalenceReceipt(
        scope=candidate.scope,
        operation=operation,
        source_context_receipt_ref=inputs.source_ref,
        candidate_baseline_ref=inputs.candidate_ref,
        checks_ref=inputs.checks_ref,
        status=status,
        **fields,
    )
