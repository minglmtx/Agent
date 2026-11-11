"""Private complete startup HTTP evidence; never an initialized task or permit."""

import base64
import hashlib
from typing import Literal, Self

from pydantic import Field, model_validator

from .process_identity import ProcessIdentity
from .state_scope import StateScope
from .validation import Contract, Sha256


class MapStartupHttpResponse(Contract):
    schema_version: Literal["map-startup-http-response/1"] = (
        "map-startup-http-response/1"
    )
    port: int = Field(ge=1024, le=65535)
    path: str = Field(min_length=1, max_length=4096)
    status: int = Field(ge=100, le=599)
    body_base64: str = Field(max_length=5592408)
    body_sha256: Sha256
    body_size_bytes: int = Field(ge=0, le=4 * 1024**2)

    @model_validator(mode="after")
    def complete_failure(self) -> Self:
        if (
            self.status == 200
            or not self.path.startswith("/")
            or self.path.startswith("//")
            or any(ord(c) <= 32 or c == "\\" for c in self.path)
        ):
            raise ValueError(
                "Exact original failed local HTTP startup request required"
            )
        body = base64.b64decode(self.body_base64, validate=True)
        if (
            len(body) != self.body_size_bytes
            or hashlib.sha256(body).hexdigest() != self.body_sha256
            or base64.b64encode(body).decode() != self.body_base64
        ):
            raise ValueError("Complete canonical original HTTP response required")
        return self


class MapStartupHttpFailureRecord(Contract):
    schema_version: Literal["map-startup-http-failure/1"] = "map-startup-http-failure/1"
    scope: StateScope
    instance_id: str = Field(min_length=1, max_length=128)
    configuration_sha256: Sha256
    writer: ProcessIdentity
    response: MapStartupHttpResponse
