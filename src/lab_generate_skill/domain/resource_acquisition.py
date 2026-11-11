"""Frozen resource acquisition intent; data does not grant launch permission.

The configuration reference identifies a complete provider-specific launch
specification. Its actual semantics/release/owner admission belong to the
provider authority. The journal binds these exact bytes before any effect.
"""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract
from .evidence import EvidenceRef
from .lifecycle import AllocationToken, OperationContext


class ResourceAcquisitionIntent(Contract):
    schema_version: Literal["resource-acquisition-intent/1"] = (
        "resource-acquisition-intent/1"
    )
    token: AllocationToken
    operation: OperationContext
    configuration_ref: EvidenceRef

    @model_validator(mode="after")
    def identity(self) -> Self:
        op, token = self.operation, self.token
        if op.mode != "execute" or (
            op.run_id,
            op.owner_id,
            op.attempt_id,
            op.allocation_id,
            op.recovery_ref,
        ) != (
            token.owner.run_id,
            token.owner.owner_id,
            token.attempt_id,
            token.allocation_id,
            token.recovery_ref,
        ):
            raise ValueError("Acquisition needs the original execute allocation")
        if self.configuration_ref.visibility != "private":
            raise ValueError("Acquisition configuration must remain private")
        return self
