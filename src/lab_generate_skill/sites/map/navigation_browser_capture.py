"""Fixed initial/terminal passive captures on the existing BrowserPageCollector."""

from typing import Any
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .navigation_browser_initialization import MapNavigationBrowserInitializer
from .navigation_initial_rules import same_start_document
from .navigation_page_capture import navigation_page


class NavigationBrowserCapture:
    def __init__(self, initial: MapNavigationBrowserInitializer) -> None:
        self.initial = initial
        self.attempted: set[str] = set()

    def collect(
        self,
        page: Any,
        collector_id: str,
        collector_version: str,
        control: OperationControl,
    ) -> str:
        initial = self.initial
        initial.check_owner()
        if collector_version != "1" or collector_id not in (
            "map-navigation-initial",
            "map-navigation-page-health",
        ):
            raise ValueError("Unsupported fixed navigation collector/version")
        if (
            page is not initial.page
            or initial.fact is None
            or initial.error is not None
            or initial.task is None
        ):
            raise OwnershipConflict("Original completed navigation setup required")
        if collector_id in self.attempted:
            raise InvalidTransition("Original navigation capture already attempted")
        if (
            collector_id == "map-navigation-page-health"
            and "map-navigation-initial" not in self.attempted
        ):
            raise InvalidTransition("Original initial capture required before terminal")
        control.checkpoint()
        self.attempted.add(collector_id)
        if collector_id == "map-navigation-initial":
            if not same_start_document(initial.task, page.url):
                raise OwnershipConflict(
                    "Navigation initial document changed before original capture"
                )
            return initial.fact.model_dump_json()
        return navigation_page(page, control).model_dump_json()
