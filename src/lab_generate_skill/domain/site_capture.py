"""Explicit read-only collector request over the original task inspect identity."""

import hashlib
from typing import Literal, Self
from pydantic import model_validator
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .validation import Contract, Identifier, NonEmptyText, Sha256
from .site_task import SiteTaskRequest
from .site_worker import SiteWorkerConfiguration
from .lifecycle import OperationContext


class SiteCaptureRequest(Contract):
    schema_version: Literal["site-capture-request/2"] = "site-capture-request/2"
    inspection: SiteTaskRequest
    collector_id: Identifier
    collector_version: NonEmptyText
    selection_ref: EvidenceRef | None = None

    @model_validator(mode="after")
    def original_inspection(self) -> Self:
        if self.inspection.action != "inspect":
            raise ValueError("Capture requires the original read-only task identity")
        if (self.collector_id, self.collector_version) == ("map-native-reference", "1"):
            if self.inspection.task.site != "map" or self.selection_ref is None:
                raise ValueError(
                    "Map reference capture requires its explicit private selection"
                )
            private_state_ref(self.selection_ref, "map-reference-selection/1")
            if (
                self.selection_ref.media_type != "application/json"
                or not 0 < self.selection_ref.size_bytes <= 65536
            ):
                raise ValueError("Bounded JSON Map reference selection required")
        elif self.selection_ref is not None:
            raise ValueError("This collector does not consume a selection reference")
        return self

    @property
    def operation(self) -> OperationContext:
        return self.inspection.operation

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    def check_site(self, configuration: SiteWorkerConfiguration) -> None:
        self.inspection.check_site(configuration)


class SiteCaptureIntent(Contract):
    schema_version: Literal["site-capture-intent/2"] = "site-capture-intent/2"
    configuration_sha256: Sha256
    request: SiteCaptureRequest
