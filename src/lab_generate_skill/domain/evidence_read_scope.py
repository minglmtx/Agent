"""A held original store read scope; this declaration does not grant access."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .evidence_sessions import EvidenceSessionBinding
from .evidence_storage import EvidenceStorageConfig
from .process_identity import ProcessIdentity
from .lifecycle import OperationContext


class EvidenceReadScope(Contract):
    schema_version: Literal["evidence-read-scope/1"] = "evidence-read-scope/1"
    binding: EvidenceSessionBinding
    config: EvidenceStorageConfig
    controller: ProcessIdentity
    operation: OperationContext
    revision: int = Field(ge=0)

    @model_validator(mode="after")
    def original(self) -> Self:
        op, owner = self.operation, self.binding.owner
        if (self.binding.storage_id, self.binding.storage_config_sha256) != (
            self.config.storage_id,
            self.config.sha256,
        ):
            raise ValueError("Read scope changed original storage configuration")
        if (
            op.run_id,
            op.owner_id,
            op.attempt_id,
            op.allocation_id,
            op.recovery_ref,
            op.cancellation_ref,
            op.mode,
        ) != (owner.run_id, owner.owner_id, None, None, None, None, "execute"):
            raise ValueError(
                "Read scope requires the original neutral metadata operation"
            )
        return self
