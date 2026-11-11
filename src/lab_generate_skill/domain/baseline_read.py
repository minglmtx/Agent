"""One exact immutable baseline graph; no state or resource permission."""

import hashlib
from typing import Literal, Self
from pydantic import Field, model_validator
from .baseline import BaselineInputs, BaselineReceipt, assemble_baseline
from .evidence import EvidenceRef
from .evidence_dependencies import evidence_references
from .lifecycle import OperationContext, RecoveryPlan
from .validation import Contract


class BaselineReadRequest(Contract):
    schema_version: Literal["baseline-read-request/1"] = "baseline-read-request/1"
    receipt: BaselineReceipt
    operation: OperationContext

    @model_validator(mode="after")
    def original_owner(self) -> Self:
        scope = self.receipt.scope
        op = self.operation
        if (op.run_id, op.owner_id) != (scope.owner.run_id, scope.owner.owner_id) or (
            op.attempt_id is not None and op.attempt_id != scope.attempt_id
        ):
            raise ValueError("Baseline proof changed original owner/attempt")
        return self


class BaselineReadBody(Contract):
    reference: EvidenceRef
    json_text: str = Field(min_length=1, max_length=2 * 1024**2)

    @model_validator(mode="after")
    def complete(self) -> Self:
        raw = self.json_text.encode()
        if self.reference.media_type != "application/json" or (
            len(raw),
            hashlib.sha256(raw).hexdigest(),
        ) != (self.reference.size_bytes, self.reference.sha256):
            raise ValueError("Baseline input body changed complete original bytes")
        return self


def baseline_documents(
    inputs: BaselineInputs,
) -> tuple[tuple[EvidenceRef, Contract], ...]:
    return (
        (inputs.spec_ref, inputs.spec),
        (inputs.environment_ref, inputs.environment),
        (inputs.prepared_ref, inputs.prepared),
        (inputs.preparation_ref, inputs.preparation),
        (inputs.initial_ref, inputs.initial),
        (inputs.prepared.task_binding_ref, inputs.binding),
        (inputs.binding.public_task_ref, inputs.public_task),
        (inputs.observation_ref, inputs.observation),
    )


def require_baseline_recoveries(
    inputs: BaselineInputs,
    receipt: BaselineReceipt,
    task: RecoveryPlan,
    environment: RecoveryPlan,
) -> None:
    for recovery, attempt, coverage in (
        (task, receipt.scope.attempt_id, inputs.spec.task_reset_checks),
        (environment, None, inputs.spec.environment_reset_checks),
    ):
        if (
            recovery.owner != receipt.scope.owner
            or recovery.attempt_id != attempt
            or recovery.state_coverage != coverage
        ):
            from .errors import OwnershipConflict

            raise OwnershipConflict(
                "Initial recovery must preserve owner, scope and complete declared coverage"
            )


class BaselineReadBodies(Contract):
    schema_version: Literal["baseline-read-bodies/1"] = "baseline-read-bodies/1"
    request: BaselineReadRequest
    inputs: BaselineInputs
    bodies: tuple[BaselineReadBody, ...] = Field(min_length=1, max_length=10)
    verified: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def original(self) -> Self:
        receipt, inputs = self.request.receipt, self.inputs
        if assemble_baseline(inputs, receipt.operation) != receipt:
            raise ValueError("Baseline proof changed original complete inputs")
        documents = {item.reference: item.json_text for item in self.bodies}
        if len(documents) != len(self.bodies):
            raise ValueError("Baseline proof repeated an input body")
        expected = baseline_documents(inputs)
        task_ref = inputs.prepared.recovery_ref
        env_ref = inputs.environment.allocation.recovery_ref
        if set(documents) != {ref for ref, _ in expected} | {task_ref, env_ref}:
            raise ValueError("Baseline proof omitted or substituted input bodies")
        for reference, value in expected:
            if type(value).model_validate_json(documents[reference]) != value:
                raise ValueError("Baseline input body differs from decoded facts")
        task = RecoveryPlan.model_validate_json(documents[task_ref])
        environment = RecoveryPlan.model_validate_json(documents[env_ref])
        require_baseline_recoveries(inputs, receipt, task, environment)
        required = set(evidence_references((inputs, task, environment)))
        if len(set(self.verified)) != len(self.verified) or not required <= set(
            self.verified
        ):
            raise ValueError("Baseline proof omitted original dependencies")
        return self
