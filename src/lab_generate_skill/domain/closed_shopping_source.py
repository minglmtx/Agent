"""Original closed category source references; no live caller permission."""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract
from .evidence import EvidenceRef
from .initial_observation import InitialObservationSelection
from .site_resource import SiteResourceSpec
from .browser_resource import BrowserResourceSpec
from .lifecycle import ResourceRecord
from .state_scope import private_state_ref
from .shopping_navigation_browser_initialization import ShoppingCategoryInitialization


class ClosedCategoryNavigationReadMaterial(Contract):
    schema_version: Literal["closed-shopping-category-read-material/1"] = (
        "closed-shopping-category-read-material/1"
    )
    context_ref: EvidenceRef
    environment_ref: EvidenceRef
    reset_ref: EvidenceRef
    initial: InitialObservationSelection
    capture_intent_ref: EvidenceRef
    capture_result_ref: EvidenceRef
    site: SiteResourceSpec
    browser: BrowserResourceSpec
    site_record: ResourceRecord
    browser_record: ResourceRecord

    @model_validator(mode="after")
    def closed(self) -> Self:
        for ref, schema in (
            (self.context_ref, "public-context-receipt/1"),
            (self.environment_ref, "environment-selection/1"),
            (self.reset_ref, "reset-selection/1"),
            (self.capture_intent_ref, "browser-capture-intent/1"),
            (self.capture_result_ref, "browser-capture-result/1"),
        ):
            private_state_ref(ref, schema)
        selected = self.browser.configuration.initialization
        scope = self.browser.configuration.spec.scope
        if (
            self.site.configuration.site_id != "shopping"
            or not isinstance(selected, ShoppingCategoryInitialization)
            or self.site_record.token != self.site.token
            or self.browser_record.token != self.browser.token
            or self.site_record.state != "closed"
            or self.browser_record.state != "closed"
            or self.site.token.owner != self.browser.token.owner
            or scope.owner != self.site.token.owner
            or self.browser.token.attempt_id != scope.attempt_id
            or selected.prepared_ref != self.initial.preparation.prepared_ref
        ):
            raise ValueError("Original closed category site/browser/source required")
        selected.check(self.browser.configuration.spec)
        return self
