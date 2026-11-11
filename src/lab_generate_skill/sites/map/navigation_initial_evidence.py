"""Original readiness captured before the sole public browser initial readout."""

from typing import Literal
from pydantic import Field
from lab_generate_skill.domain.validation import Contract, NonEmptyText
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from .navigation_page_schema import NavigationPageHealth


class NavigationInitialReadiness(Contract):
    schema_version: Literal["map-navigation-initial-readiness/1"] = (
        "map-navigation-initial-readiness/1"
    )
    initialization: MapNavigationInitialization
    start_url: NonEmptyText
    page: NavigationPageHealth
    native_signal_json: str | None
    native_view_json: str | None
    stable_seconds: float = Field(ge=0, allow_inf_nan=False)
