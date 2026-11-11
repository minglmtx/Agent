"""Pure selected page-health facts; no browser or site-operation imports."""

from typing import Literal
from pydantic import Field
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from pydantic import model_validator
from typing import Self
from .product_catalog_contract import ProductCatalogState as ProductCatalogState
from .tasks.product_description_spec import (
    ProductDescriptionSpec as ProductDescriptionSpec,
)


class AdminPageHealth(Contract):
    schema_version: Literal["admin-page-health/1"] = "admin-page-health/1"
    url: str = Field(min_length=1, max_length=65536)
    login: bool
    page_error: bool


class SiteCaptureEvidence(Contract):
    intent_ref: EvidenceRef
    result_ref: EvidenceRef

    @model_validator(mode="after")
    def references(self) -> Self:
        private_state_ref(self.intent_ref, "site-capture-intent/2")
        private_state_ref(self.result_ref, "site-task-result/1")
        return self


class PageCaptureEvidence(Contract):
    intent_ref: EvidenceRef
    result_ref: EvidenceRef

    @model_validator(mode="after")
    def references(self) -> Self:
        private_state_ref(self.intent_ref, "browser-capture-intent/1")
        private_state_ref(self.result_ref, "browser-capture-result/1")
        return self


class ProductDescriptionEvidence(Contract):
    schema_version: Literal["admin-product-description-evidence/1"] = (
        "admin-product-description-evidence/1"
    )
    before: SiteCaptureEvidence | None
    after: SiteCaptureEvidence | None
    page: PageCaptureEvidence | None
    trace_ref: EvidenceRef | None

    @model_validator(mode="after")
    def trace_reference(self) -> Self:
        if self.trace_ref is not None:
            private_state_ref(self.trace_ref, "interaction-trace/1")
        return self


from .navigation_evidence_schema import (
    AdminNavigationPage as AdminNavigationPage,
    AdminNavigationSpec as AdminNavigationSpec,
)

from .navigation_evaluation_schema import (
    AdminNavigationEvidence as AdminNavigationEvidence,
)
