"""Frozen observation settings; a declaration grants no tool or runtime right."""

import hashlib
from typing import Literal, Self
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from typing import Any
from .validation import Contract, Identifier


class ObservationReadPolicy(Contract):
    schema_version: Literal[
        "observation-read-policy/1", "observation-read-policy/2"
    ] = "observation-read-policy/1"
    max_consecutive_invalid_proposals: int | None = Field(default=None, ge=1, le=64)
    max_identical_invalid_proposals: int | None = Field(default=None, ge=1, le=64)
    policy_id: Identifier
    unicode_version: str = Field(min_length=1, max_length=32, pattern=r"^[0-9.]+$")
    switch_tokens: int = Field(ge=1, le=61440)
    body_target_tokens: int = Field(ge=1, le=61440)
    body_max_tokens: int = Field(ge=1, le=61440)
    reads_per_observation: int = Field(ge=1, le=64)
    warn_remaining: int = Field(ge=1, le=64)
    consecutive_no_progress: int = Field(ge=1, le=64)
    max_ranges: int = Field(ge=1, le=16)
    directory_entries: int = Field(ge=1, le=128)
    search_hits: int = Field(ge=1, le=128)
    page_units: int = Field(ge=1, le=128)
    max_source_lines: int = Field(ge=1, le=100000)
    search_mode: Literal["unicode_casefold_literal/1"] = "unicode_casefold_literal/1"
    window_mode: Literal["single_active_window/1"] = "single_active_window/1"

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.schema_version == "observation-read-policy/1":
            result.pop("max_consecutive_invalid_proposals", None)
            result.pop("max_identical_invalid_proposals", None)
        return result

    @model_validator(mode="after")
    def distinct_limits(self) -> Self:
        fields = (
            "max_consecutive_invalid_proposals",
            "max_identical_invalid_proposals",
        )
        if self.schema_version == "observation-read-policy/1":
            if any(name in self.model_fields_set for name in fields):
                raise ValueError("Original read policy forbids new rejection fields")
        elif any(getattr(self, name) is None for name in fields):
            raise ValueError(
                "Read policy2 requires both explicit frozen rejection limits"
            )
        if self.body_target_tokens > self.body_max_tokens:
            raise ValueError("Observation body target exceeds its distinct maximum")
        if self.warn_remaining >= self.reads_per_observation:
            raise ValueError("Remaining-read hint must precede quota exhaustion")
        if self.consecutive_no_progress > self.reads_per_observation:
            raise ValueError("No-progress limit exceeds original read quota")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()
