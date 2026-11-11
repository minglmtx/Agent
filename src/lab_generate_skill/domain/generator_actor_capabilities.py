"""Public selected-Actor behavior, without private configuration or source refs."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract


class GeneratorActorReadLimits(Contract):
    body_target_tokens: int = Field(ge=1, le=61440)
    body_max_tokens: int = Field(ge=1, le=61440)
    reads_per_observation: int = Field(ge=1, le=64)
    warn_remaining: int = Field(ge=0, le=63)
    consecutive_no_progress: int = Field(ge=1, le=64)
    max_ranges: int = Field(ge=1, le=16)
    search_mode: Literal["unicode_casefold_literal/1"] = "unicode_casefold_literal/1"

    @model_validator(mode="after")
    def consistent_limits(self) -> Self:
        if (
            self.body_target_tokens > self.body_max_tokens
            or self.warn_remaining >= self.reads_per_observation
        ):
            raise ValueError("Public limits must retain the selected Actor bounds")
        return self


class GeneratorActorCapabilities(Contract):
    schema_version: Literal["generator-actor-capabilities/1"] = (
        "generator-actor-capabilities/1"
    )
    observation_mode: Literal[
        "current_page_full_ax",
        "compact_full_ax",
        "adaptive_compact_full_or_local",
        "current_task_structured_map",
    ]
    conditional_read_tools: tuple[
        Literal["list_regions", "read_region", "search_regions"], ...
    ] = Field(max_length=3)
    read_limits: GeneratorActorReadLimits | None

    @model_validator(mode="after")
    def actual_conditional_interfaces(self) -> Self:
        local = self.observation_mode == "adaptive_compact_full_or_local"
        expected = ("list_regions", "read_region", "search_regions") if local else ()
        if self.conditional_read_tools != expected or local != (
            self.read_limits is not None
        ):
            raise ValueError(
                "Only a supported selected local Actor declares conditional read tools"
            )
        return self
