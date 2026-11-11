"""Complete passive navigation page facts; no inferred HTTP or target result."""

from typing import Literal
from pydantic import Field
from lab_generate_skill.domain.validation import Contract
from .page_health import MapPageHealth


class NavigationPageHealth(Contract):
    schema_version: Literal["map-navigation-page-health/1"] = (
        "map-navigation-page-health/1"
    )
    health: MapPageHealth
    heading_texts: tuple[str, ...] = Field(max_length=100000)
    document_state: Literal["loading", "interactive", "complete"]

    def original_page(self) -> dict[str, object]:
        return {
            **self.health.model_dump(mode="json"),
            "heading_texts": list(self.heading_texts),
        }
