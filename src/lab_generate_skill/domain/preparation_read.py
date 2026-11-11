"""Exact preparation inputs from one bounded read; no current permission."""

import hashlib
from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .preparation_record import PreparationSelection, PreparationInputs
from .lifecycle import OperationContext
from .evidence import EvidenceRef


class PreparationReadRequest(Contract):
    schema_version: Literal["preparation-read-request/1"] = "preparation-read-request/1"
    selection: PreparationSelection
    operation: OperationContext


class PreparationReadBodies(Contract):
    schema_version: Literal["preparation-read-bodies/1"] = "preparation-read-bodies/1"
    request: PreparationReadRequest
    inputs: PreparationInputs
    verified: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=256)
    private_spec_json: str = Field(min_length=1, max_length=2 * 1024**2)
    snapshot_json: str = Field(min_length=1, max_length=8 * 1024**2)

    @model_validator(mode="after")
    def original(self) -> Self:
        if self.inputs.selection != self.request.selection:
            raise ValueError("Preparation read changed original selection")
        snapshot = self.inputs.request.snapshot_ref
        if snapshot is None:
            raise ValueError("Original preparation snapshot required")
        for reference, text in (
            (self.inputs.binding.private_spec_ref, self.private_spec_json),
            (snapshot, self.snapshot_json),
        ):
            raw = text.encode()
            if (len(raw), hashlib.sha256(raw).hexdigest()) != (
                reference.size_bytes,
                reference.sha256,
            ):
                raise ValueError("Preparation proof changed complete original bytes")
        required = {
            self.request.selection.request_ref,
            self.request.selection.result_ref,
            self.request.selection.environment_ref,
            self.inputs.request.binding_ref,
            self.inputs.binding.public_task_ref,
            self.inputs.binding.private_spec_ref,
            self.inputs.binding.baseline_ref,
            snapshot,
            self.inputs.request.operation.recovery_ref,
        }
        if len(set(self.verified)) != len(self.verified) or not required <= set(
            self.verified
        ):
            raise ValueError("Preparation proof omitted original dependencies")
        return self
