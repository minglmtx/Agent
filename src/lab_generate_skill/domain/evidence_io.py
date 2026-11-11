"""Pure physical evidence request descriptor, shared by wire and durable intent.

Describes the original operation only; neither stored bytes nor permission to
execute/replay it. Wire framing and actual filesystem effects stay in adapters.
"""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from .evidence import EvidenceMetadata, EvidenceRef
from .validation import Contract, Identifier

MAX_OBJECT_BYTES = 64 * 1024 * 1024


class EvidenceCommand(Contract):
    schema_version: Literal["evidence-io-command/1"] = "evidence-io-command/1"
    exchange_id: Identifier
    operation: Literal["read", "put"]
    root: str = Field(min_length=1, max_length=4096)
    max_object_bytes: int = Field(ge=1, le=MAX_OBJECT_BYTES)
    reference: EvidenceRef
    metadata: EvidenceMetadata | None = None

    @model_validator(mode="after")
    def check_request(self) -> Self:
        path = PurePosixPath(self.root)
        if not path.is_absolute() or "\0" in self.root or ".." in path.parts:
            raise ValueError("Worker root must be a trusted absolute POSIX path")
        if self.reference.uri != f"cas://sha256/{self.reference.sha256}":
            raise ValueError("Worker reference must use canonical CAS location")
        if self.reference.size_bytes > self.max_object_bytes:
            raise ValueError("Expected evidence exceeds object budget")
        if (self.operation == "put") != (self.metadata is not None):
            raise ValueError("Only put requires metadata")
        if self.metadata is not None and any(
            getattr(self.metadata, name) != getattr(self.reference, name)
            for name in ("media_type", "content_schema", "visibility", "producer")
        ):
            raise ValueError("Physical descriptor metadata differs from reference")
        return self
