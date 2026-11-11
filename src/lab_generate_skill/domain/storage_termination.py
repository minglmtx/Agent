"""Original controller's observed reap, not independent storage-clean authority."""

import hashlib
from typing import Literal, Self
from pydantic import AwareDatetime, Field, model_validator
from .process_identity import ProcessIdentity
from .validation import Contract, Sha256


class StorageProcessEnd(Contract):
    schema_version: Literal["storage-process-end/1"] = "storage-process-end/1"
    controller: ProcessIdentity
    request_sha256: Sha256
    process_id: int = Field(ge=1)
    returncode: int
    observed_at: AwareDatetime
    capture_sha256: Sha256
    kill_requested: bool

    @model_validator(mode="after")
    def distinct_child(self) -> Self:
        if self.process_id == self.controller.process_id:
            raise ValueError("Storage ending must describe a distinct child")
        return self

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()
