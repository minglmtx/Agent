"""Selected terminal document facts; unknown transport is never assumed healthy."""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract


class MapPageHealth(Contract):
    schema_version: Literal["map-page-health/1"] = "map-page-health/1"
    url: str = Field(min_length=1, max_length=65536)
    sampled_url: str = Field(min_length=1, max_length=65536)
    title: str = Field(max_length=65536)
    http_status: int | None = Field(ge=100, le=599)
    status_source: Literal["navigation_timing", "unavailable", "document_changed"]
    login_page: bool
    error_page: bool

    @model_validator(mode="after")
    def original_document(self) -> Self:
        if (self.http_status is not None) != (
            self.status_source == "navigation_timing"
        ):
            raise ValueError(
                "Native current document status or explicit unknown required"
            )
        if (self.sampled_url != self.url) != (self.status_source == "document_changed"):
            raise ValueError("Changed document must remain explicit unknown")
        return self
