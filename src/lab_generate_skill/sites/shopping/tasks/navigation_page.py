"""Category DOM facts; existing ETA health wire remains unchanged."""

from typing import Literal
from lab_generate_skill.domain.validation import Contract, NonEmptyText
from ..evidence_schema import ShoppingPageHealth


class CategoryNavigationBlock(Contract):
    source: Literal["local_network_policy"]
    reason: Literal["outside_declared_local_services"]
    document_url: Literal["chrome-error://chromewebdata/"]
    blocked_origin: NonEmptyText


class CategoryNavigationPage(Contract):
    schema_version: Literal["shopping-category-navigation-page/1"] = (
        "shopping-category-navigation-page/1"
    )
    health: ShoppingPageHealth
    heading_texts: tuple[str, ...]
    document_ready: Literal["loading", "interactive", "complete"]
    navigation_policy_block: CategoryNavigationBlock | None = None
