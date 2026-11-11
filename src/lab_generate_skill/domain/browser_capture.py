"""Private read-only facts from the original browser after a named observation."""

from datetime import datetime
import hashlib
from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract, Identifier, NonEmptyText, Sha256
from .state_scope import StateScope
from .lifecycle import OperationContext
from .browser_session import BrowserSessionSpec, BrowserReadout
from .errors import OwnershipConflict


class BrowserCaptureRequest(Contract):
    schema_version: Literal["browser-capture-request/1"] = "browser-capture-request/1"
    scope: StateScope
    operation: OperationContext
    observation_sha256: Sha256
    collector_id: Identifier
    collector_version: NonEmptyText

    @model_validator(mode="after")
    def original_scope(self) -> Self:
        if (
            self.operation.run_id,
            self.operation.owner_id,
            self.operation.attempt_id,
            self.operation.mode,
        ) != (
            self.scope.owner.run_id,
            self.scope.owner.owner_id,
            self.scope.attempt_id,
            "execute",
        ):
            raise ValueError("Browser capture requires original execution scope")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    def check_readout(self, spec: BrowserSessionSpec, readout: BrowserReadout) -> None:
        if (
            self.scope != spec.scope
            or readout.scope != self.scope
            or self.observation_sha256
            != hashlib.sha256(
                readout.observation.model_dump_json().encode()
            ).hexdigest()
        ):
            raise OwnershipConflict(
                "Capture changed original browser or latest observation"
            )


class BrowserCaptureIntent(Contract):
    schema_version: Literal["browser-capture-intent/1"] = "browser-capture-intent/1"
    configuration_sha256: Sha256
    request: BrowserCaptureRequest


class BrowserCaptureResult(Contract):
    schema_version: Literal["browser-capture-result/1"] = "browser-capture-result/1"
    request_sha256: Sha256
    captured_at: datetime
    private_result: str = Field(min_length=2, max_length=262144)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if (
            self.captured_at.tzinfo is None
            or len(self.private_result.encode()) > 262144
        ):
            raise ValueError("Capture needs aware time and bounded private bytes")
        return self
