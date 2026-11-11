"""Pure selected Shopping capture selection/data; no browser or native effects."""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from .tasks.order_eta_spec import OrderEtaSpec as OrderEtaSpec
from .tasks.order_eta_state import (
    OrderEtaState as OrderEtaState,
    OrderEtaExecutionInput as OrderEtaExecutionInput,
)


class ShoppingPageHealth(Contract):
    schema_version: Literal["shopping-page-health/1"] = "shopping-page-health/1"
    url: str = Field(min_length=1, max_length=65536)
    http_status: int | None = Field(ge=100, le=599)
    status_source: Literal["navigation_timing", "unavailable", "document_changed"]
    title: str = Field(max_length=65536)
    login_page: bool
    error_page: bool

    @model_validator(mode="after")
    def actual_status(self) -> Self:
        if (self.status_source == "navigation_timing") != (
            self.http_status is not None
        ):
            raise ValueError("Measured native status or explicit unknown required")
        return self


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


class OrderEtaEvidence(Contract):
    schema_version: Literal["shopping-order-eta-evidence/1"] = (
        "shopping-order-eta-evidence/1"
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
