"""Original acquired site facts required by private artifact storage admission."""

from typing import Literal, Self
from pydantic import field_validator, model_validator
from .validation import Contract, Sha256
from .lifecycle import AllocationToken, OperationContext, ResourceRecord
from .site_resource import SiteResourceSpec, SiteResourceReady
from .resource_acquisition import ResourceAcquisitionIntent
from .errors import OwnershipConflict


class SiteAcquiredDetails(Contract):
    ready: SiteResourceReady
    site_started: Literal[False]

    @field_validator("site_started", mode="before")
    @classmethod
    def before_native_start(cls, value: object) -> object:
        if value is not False:
            raise ValueError("Original worker acquisition must precede native startup")
        return value


class SiteAcquiredFact(Contract):
    schema_version: Literal["site-resource-fact/1"] = "site-resource-fact/1"
    spec_sha256: Sha256
    token: AllocationToken
    operation: OperationContext
    state: Literal["acquired"]
    details: SiteAcquiredDetails


class SiteStorageOriginal(Contract):
    schema_version: Literal["site-storage-original/1"] = "site-storage-original/1"
    record: ResourceRecord
    intent: ResourceAcquisitionIntent
    spec: SiteResourceSpec
    acquired: SiteAcquiredFact

    @model_validator(mode="after")
    def original_scope(self) -> Self:
        import hashlib

        record, intent, spec, acquired = (
            self.record,
            self.intent,
            self.spec,
            self.acquired,
        )
        acquiring = [event for event in record.events if event.state == "acquiring"]
        obtained = [event for event in record.events if event.state == "acquired"]
        if (len(acquiring), len(obtained)) != (1, 1) or not (
            record.token == intent.token == spec.token == acquired.token
            and acquiring[0].operation == intent.operation
            and obtained[0].operation == acquired.operation
            and acquired.operation.parent_operation_id == intent.operation.operation_id
            and acquired.spec_sha256
            == hashlib.sha256(spec.model_dump_json().encode()).hexdigest()
        ):
            raise OwnershipConflict(
                "Private storage lost original site acquisition provenance"
            )
        ready = acquired.details.ready
        if (
            ready.controller.target.execution != spec.slurm.execution
            or ready.worker.owner_guard.controller != spec.slurm.parent.writer
        ):
            raise OwnershipConflict("Private storage changed original Slurm/controller")
        return self
