"""Explicit navigation origin selection; immutable references confer no rights."""

from typing import Literal, Self
from urllib.parse import urlsplit
from pydantic import Field, model_validator
from .validation import Contract
from .evidence import EvidenceRef
from .state_scope import private_state_ref


class MapOriginPolicy(Contract):
    schema_version: Literal["map-origin-policy/1"] = "map-origin-policy/1"
    mode: Literal["dynamic", "frozen_context"]
    source_context_receipt_ref: EvidenceRef | None
    source_context_ref: EvidenceRef | None
    source_start_url: str | None = Field(max_length=4096)

    @model_validator(mode="after")
    def original(self) -> Self:
        refs = (
            self.source_context_receipt_ref,
            self.source_context_ref,
            self.source_start_url,
        )
        if self.mode == "dynamic":
            if any(x is not None for x in refs):
                raise ValueError("Dynamic origin cannot claim a frozen source")
            return self
        if any(x is None for x in refs):
            raise ValueError(
                "Frozen origin needs complete original context references/URL"
            )
        assert (
            self.source_context_receipt_ref is not None
            and self.source_context_ref is not None
            and self.source_start_url is not None
        )
        private_state_ref(self.source_context_receipt_ref, "public-context-receipt/1")
        if (
            self.source_context_ref.content_schema,
            self.source_context_ref.visibility,
            self.source_context_ref.media_type,
        ) != ("public-construction-context/1", "public", "application/json"):
            raise ValueError("Original public source context required")
        start = urlsplit(self.source_start_url)
        if (
            start.scheme != "http"
            or start.hostname != "127.0.0.1"
            or start.username is not None
            or start.password is not None
            or start.port is None
            or start.netloc != f"127.0.0.1:{start.port}"
            or not 1024 <= start.port <= 65535
            or any(ord(x) < 33 for x in self.source_start_url)
        ):
            raise ValueError("Exact canonical native loopback source URL required")
        return self

    @classmethod
    def dynamic(cls) -> "MapOriginPolicy":
        return cls(
            mode="dynamic",
            source_context_receipt_ref=None,
            source_context_ref=None,
            source_start_url=None,
        )

    @property
    def requested_web_port(self) -> int | None:
        return (
            None
            if self.source_start_url is None
            else urlsplit(self.source_start_url).port
        )
