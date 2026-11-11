"""Private paid-send envelope; only exact input/parameter bytes reach transport.

This envelope is not a prompt and constructing it grants no dispatch permission.
Role projection, provider compatibility and original writer/claim authorization
must be verified before reserve; the sender obtains its own durable permit.
"""

import hashlib
from typing import Literal, Self
from pydantic import Field, model_validator
from .evidence import EvidenceRef
from .generation import Reservation, RequestIdentity
from .lifecycle import OperationContext
from .state_scope import private_state_ref
from .validation import Contract


def check_model_operation(request: RequestIdentity, op: OperationContext) -> None:
    if (op.run_id, op.owner_id, op.attempt_id) != (
        request.owner.run_id,
        request.owner.owner_id,
        request.attempt_id,
    ):
        raise ValueError("Model operation must retain original request scope")


def check_model_cleanup(original: OperationContext, cleanup: OperationContext) -> None:
    if (
        cleanup.mode != "cleanup"
        or cleanup.parent_operation_id != original.operation_id
        or (
            cleanup.run_id,
            cleanup.owner_id,
            cleanup.attempt_id,
            cleanup.allocation_id,
            cleanup.recovery_ref,
        )
        != (
            original.run_id,
            original.owner_id,
            original.attempt_id,
            original.allocation_id,
            original.recovery_ref,
        )
    ):
        raise ValueError("Settlement requires bounded cleanup for the original send")


class ModelSendLimits(Contract):
    max_input_bytes: int = Field(ge=1, le=64 * 1024 * 1024)
    max_parameters_bytes: int = Field(ge=1, le=64 * 1024 * 1024)
    max_response_bytes: int = Field(ge=1, le=64 * 1024 * 1024)


class ModelSendPlan(Contract):
    schema_version: Literal["model-send-plan/1"] = "model-send-plan/1"
    reservation: Reservation
    input_ref: EvidenceRef
    parameters_ref: EvidenceRef
    limits: ModelSendLimits
    reserve_operation: OperationContext
    operation: OperationContext
    settlement_operation: OperationContext

    @model_validator(mode="after")
    def frozen_binding(self) -> Self:
        request = self.reservation.request
        private_state_ref(self.input_ref, request.role + "-model-input/1")
        private_state_ref(self.parameters_ref, "model-parameters/1")
        if (self.input_ref.sha256, self.parameters_ref.sha256) != (
            request.input_sha256,
            request.parameters_sha256,
        ):
            raise ValueError("Model input and parameters must match request digests")
        if not 0 < self.input_ref.size_bytes <= self.limits.max_input_bytes or not (
            0 < self.parameters_ref.size_bytes <= self.limits.max_parameters_bytes
        ):
            raise ValueError("Model input/parameters exceed frozen byte limits")
        ops = (self.reserve_operation, self.operation, self.settlement_operation)
        for op in ops:
            check_model_operation(request, op)
        if len({op.operation_id for op in ops}) != 3:
            raise ValueError("Reserve, send and settlement operations must differ")
        if self.reserve_operation.mode != "execute" or self.operation.mode != "execute":
            raise ValueError("Cleanup cannot arrange a new paid send")
        check_model_cleanup(self.operation, self.settlement_operation)
        return self


class ResolvedModelRequest(Contract):
    """Exact stored bytes, not a container of private task/claim/budget objects."""

    request: RequestIdentity
    input_bytes: bytes = Field(min_length=1)
    parameters_bytes: bytes = Field(min_length=1)
    limits: ModelSendLimits

    @model_validator(mode="after")
    def exact_bytes(self) -> Self:
        if (
            hashlib.sha256(self.input_bytes).hexdigest(),
            hashlib.sha256(self.parameters_bytes).hexdigest(),
        ) != (self.request.input_sha256, self.request.parameters_sha256):
            raise ValueError("Transport bytes must match original request digests")
        if (
            len(self.input_bytes) > self.limits.max_input_bytes
            or len(self.parameters_bytes) > self.limits.max_parameters_bytes
        ):
            raise ValueError("Transport inputs exceed frozen limits")
        return self
