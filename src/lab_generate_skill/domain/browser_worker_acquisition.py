"""Original browser worker ownership before navigation; no initial readiness."""

import hashlib
from typing import Literal, Self
from pydantic import field_validator, model_validator
from .validation import Contract, Sha256
from .browser_resource import BrowserResourceSpec, BrowserResourcePrepared
from .lifecycle import AllocationToken, OperationContext
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .errors import OwnershipConflict


class BrowserWorkerAcquiredDetails(Contract):
    prepared: BrowserResourcePrepared
    prepared_ref: EvidenceRef
    browser_started: Literal[False]

    @field_validator("browser_started", mode="before")
    @classmethod
    def before_navigation(cls, value: object) -> object:
        if value is not False:
            raise ValueError("Worker acquisition must precede native browser startup")
        return value

    @model_validator(mode="after")
    def original_prepared(self) -> Self:
        private_state_ref(self.prepared_ref, "browser-resource-prepared/1")
        raw = self.prepared.model_dump_json().encode()
        if (self.prepared_ref.sha256, self.prepared_ref.size_bytes) != (
            hashlib.sha256(raw).hexdigest(),
            len(raw),
        ):
            raise OwnershipConflict("Original browser prepared reference changed bytes")
        return self


class BrowserWorkerAcquiredFact(Contract):
    schema_version: Literal["browser-worker-acquired/1"] = "browser-worker-acquired/1"
    spec_sha256: Sha256
    token: AllocationToken
    operation: OperationContext
    state: Literal["acquired"] = "acquired"
    details: BrowserWorkerAcquiredDetails

    def check_spec(self, spec: BrowserResourceSpec) -> None:
        spec.check_operation(self.operation, "execute")
        prepared = self.details.prepared
        if (
            self.token != spec.token
            or self.spec_sha256
            != hashlib.sha256(spec.model_dump_json().encode()).hexdigest()
            or prepared.step.controller.target.execution != spec.slurm.execution
            or prepared.owner_guard.controller != spec.slurm.parent.writer
        ):
            raise OwnershipConflict(
                "Browser worker acquisition changed original resource"
            )
