"""Selected native image evidence; terminal capture never stands for issued AX."""

from dataclasses import dataclass
from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.trace import InteractionTrace
from .tasks.image_spec import NativeImageSpec as NativeImageSpec
from .image_state import ImageReference as ImageReference
from .native_schema import NativeCapture as NativeCapture

CHECKS = (
    "valid_native_terminal_document",
    "exactly_one_new_native_post",
    "correct_account",
    "correct_forum",
    "requested_title",
    "native_image_post",
    "requested_original_image",
    "saved_post_title_actually_observed",
)


@dataclass(frozen=True)
class ImageOutcome:
    status: Literal["success", "failure", "unknown"]
    reward: int | None
    checks: tuple[tuple[str, bool | None], ...]
    reason: str


class RedditPageHealth(Contract):
    schema_version: Literal["reddit-page-health/1"] = "reddit-page-health/1"
    url: str = Field(min_length=1, max_length=65536)
    title: str = Field(max_length=65536)
    http_status: int | None = Field(ge=100, le=599)
    status_source: Literal["navigation_timing", "unavailable", "document_changed"]
    login_page: bool
    error_page: bool

    @model_validator(mode="after")
    def actual_document_status(self) -> Self:
        if (self.status_source == "navigation_timing") != (
            self.http_status is not None
        ):
            raise ValueError("Actual document status or explicit unknown required")
        return self


class ImageSiteCapture(Contract):
    intent_ref: EvidenceRef
    result_ref: EvidenceRef

    @model_validator(mode="after")
    def refs(self) -> Self:
        private_state_ref(self.intent_ref, "site-capture-intent/2")
        private_state_ref(self.result_ref, "site-task-result/1")
        return self


class ImagePageCapture(Contract):
    intent_ref: EvidenceRef
    result_ref: EvidenceRef

    @model_validator(mode="after")
    def refs(self) -> Self:
        private_state_ref(self.intent_ref, "browser-capture-intent/1")
        private_state_ref(self.result_ref, "browser-capture-result/1")
        return self


class ImageEvidence(Contract):
    schema_version: Literal["reddit-image-evidence/1"] = "reddit-image-evidence/1"
    environment_ref: EvidenceRef | None
    browser_spec_ref: EvidenceRef | None
    before: ImageSiteCapture | None
    after: ImageSiteCapture | None
    page: ImagePageCapture | None
    trace_ref: EvidenceRef | None
    trace_snapshot_ref: EvidenceRef | None

    @model_validator(mode="after")
    def refs(self) -> Self:
        for ref, schema in (
            (self.environment_ref, "environment-selection/1"),
            (self.browser_spec_ref, "browser-resource-spec/4"),
            (self.trace_ref, "interaction-trace/1"),
            (self.trace_snapshot_ref, "trace-journal-snapshot/1"),
        ):
            if ref is not None:
                private_state_ref(ref, schema)
        return self


@dataclass(frozen=True)
class ImageFacts:
    public: PublicTask
    spec: NativeImageSpec
    reference: ImageReference
    before: NativeCapture
    after: NativeCapture
    page: RedditPageHealth
    trace: InteractionTrace
    last_issued_ax: str
