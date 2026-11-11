"""Full original browser acquisition provenance required by private file readers."""

import hashlib
from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract
from .browser_resource import BrowserResourceSpec
from .browser_worker_acquisition import BrowserWorkerAcquiredFact
from .lifecycle import ResourceRecord
from .resource_acquisition import ResourceAcquisitionIntent
from .errors import OwnershipConflict


class BrowserStorageOriginal(Contract):
    schema_version: Literal["browser-storage-original/1"] = "browser-storage-original/1"
    record: ResourceRecord
    intent: ResourceAcquisitionIntent
    spec: BrowserResourceSpec
    acquired: BrowserWorkerAcquiredFact

    @model_validator(mode="after")
    def provenance(self) -> Self:
        record, intent, spec, acquired = (
            self.record,
            self.intent,
            self.spec,
            self.acquired,
        )
        acquiring = [event for event in record.events if event.state == "acquiring"]
        obtained = [event for event in record.events if event.state == "acquired"]
        if (len(acquiring), len(obtained)) != (1, 1):
            raise OwnershipConflict(
                "Browser files require original durable worker acquisition"
            )
        if not (
            record.token == intent.token == spec.token == acquired.token
            and acquiring[0].operation == intent.operation
            and obtained[0].operation == acquired.operation
            and acquired.operation.parent_operation_id == intent.operation.operation_id
            and len(acquiring[0].evidence) == len(obtained[0].evidence) == 1
        ):
            raise OwnershipConflict(
                "Browser file access changed original acquisition lineage"
            )
        for reference, fact, schema in (
            (acquiring[0].evidence[0], intent, "resource-acquisition-intent/1"),
            (intent.configuration_ref, spec, "browser-resource-spec/4"),
            (obtained[0].evidence[0], acquired, "browser-worker-acquired/1"),
        ):
            raw = fact.model_dump_json().encode()
            if (
                reference.visibility,
                reference.media_type,
                reference.producer,
                reference.content_schema,
                reference.sha256,
                reference.size_bytes,
            ) != (
                "private",
                "application/json",
                "fixed-browser-resource",
                schema,
                hashlib.sha256(raw).hexdigest(),
                len(raw),
            ):
                raise OwnershipConflict(
                    "Browser acquisition lost exact original reference bytes"
                )
        acquired.check_spec(spec)
        if spec.configuration.map_inputs is not None and (
            spec.configuration.map_inputs.collection.operation != intent.operation
        ):
            raise OwnershipConflict(
                "Map collection changed original acquisition operation/deadline"
            )
        return self
