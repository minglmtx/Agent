"""Pure navigation evidence surface intended for the site's evidence_schema."""

from typing import Literal
from pydantic import Field
from lab_generate_skill.domain.validation import Contract
from .tasks.navigation_spec import AdminNavigationSpec as AdminNavigationSpec


class AdminNavigationPage(Contract):
    schema_version: Literal["admin-navigation-page/1"] = "admin-navigation-page/1"
    url: str = Field(min_length=1, max_length=65536)
    heading: str = Field(max_length=16384)
    login: bool
    page_error: bool
