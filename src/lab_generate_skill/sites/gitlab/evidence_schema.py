"""Original document/account facts; missing native observations remain unknown."""

from typing import Literal, Self
from dataclasses import dataclass
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.trace import InteractionTrace
from .tasks.ssh_key_spec import SshKeySpec as SshKeySpec
from .tasks.ssh_key_state import SshKeyNativeState as SshKeyNativeState

from .tasks.group_spec import GroupSpec as GroupSpec
from .tasks.group_capture import GroupCapturedFacts as GroupCapturedFacts
from .tasks.group_state import GroupNativeState as GroupNativeState

CHECKS = (
    "complete_unrelated_native_state_preserved",
    "valid_local_terminal_page",
    "exactly_one_native_key_saved",
    "supplied_key_and_title_saved",
    "key_belongs_to_current_account",
    "native_fingerprint_agrees",
    "current_account_profile_capture",
)


@dataclass(frozen=True)
class SshKeyOutcome:
    status: Literal["success", "failure", "unknown"]
    reward: int | None
    checks: tuple[bool | None, ...]
    reason: str


class GitlabPageHealth(Contract):
    schema_version: Literal["gitlab-page-health/1"] = "gitlab-page-health/1"
    url: str = Field(min_length=1, max_length=65536)
    title: str = Field(max_length=65536)
    http_status: int | None = Field(ge=100, le=599)
    status_source: Literal["navigation_timing", "unavailable", "document_changed"]
    login_page: bool
    error_page: bool
    account_id: int | None = Field(ge=1)

    @model_validator(mode="after")
    def native_status(self) -> Self:
        if (self.status_source == "navigation_timing") != (
            self.http_status is not None
        ):
            raise ValueError(
                "Actual original document status or explicit unknown required"
            )
        if self.login_page and self.account_id is not None:
            raise ValueError("Login page cannot claim authenticated current account")
        return self


class GitlabSiteCapture(Contract):
    intent_ref: EvidenceRef
    result_ref: EvidenceRef

    @model_validator(mode="after")
    def refs(self) -> Self:
        private_state_ref(self.intent_ref, "site-capture-intent/2")
        private_state_ref(self.result_ref, "site-task-result/1")
        return self


class GitlabPageCapture(Contract):
    intent_ref: EvidenceRef
    result_ref: EvidenceRef

    @model_validator(mode="after")
    def refs(self) -> Self:
        private_state_ref(self.intent_ref, "browser-capture-intent/1")
        private_state_ref(self.result_ref, "browser-capture-result/1")
        return self


class SshKeyEvidence(Contract):
    schema_version: Literal["gitlab-ssh-key-evidence/1"] = "gitlab-ssh-key-evidence/1"
    environment_ref: EvidenceRef | None
    browser_spec_ref: EvidenceRef | None
    before: GitlabSiteCapture | None
    after: GitlabSiteCapture | None
    page: GitlabPageCapture | None
    trace_ref: EvidenceRef | None

    @model_validator(mode="after")
    def refs(self) -> Self:
        for ref, schema in (
            (self.environment_ref, "environment-selection/1"),
            (self.browser_spec_ref, "browser-resource-spec/4"),
            (self.trace_ref, "interaction-trace/1"),
        ):
            if ref is not None:
                private_state_ref(ref, schema)
        return self


@dataclass(frozen=True)
class SshKeyFacts:
    public: PublicTask
    spec: SshKeySpec
    before: SshKeyNativeState
    after: SshKeyNativeState
    page: GitlabPageHealth
    trace: InteractionTrace


@dataclass(frozen=True)
class GroupOutcome:
    status: Literal["success", "failure", "unknown"]
    reward: int | None
    checks: tuple[tuple[str, bool], ...]
    reason: str | None
    state_change_requires_review: bool = False


class GroupEvidence(Contract):
    schema_version: Literal["gitlab-group-evidence/1"] = "gitlab-group-evidence/1"
    environment_ref: EvidenceRef | None
    browser_spec_ref: EvidenceRef | None
    before: GitlabSiteCapture | None
    after: GitlabSiteCapture | None
    page: GitlabPageCapture | None
    trace_ref: EvidenceRef | None

    @model_validator(mode="after")
    def refs(self) -> Self:
        for ref, schema in (
            (self.environment_ref, "environment-selection/1"),
            (self.browser_spec_ref, "browser-resource-spec/4"),
            (self.trace_ref, "interaction-trace/1"),
        ):
            if ref is not None:
                private_state_ref(ref, schema)
        return self


@dataclass(frozen=True)
class GroupFacts:
    public: PublicTask
    spec: GroupSpec
    before: GroupCapturedFacts
    after: GroupCapturedFacts
    page: GitlabPageHealth
    trace: InteractionTrace
    site_origin: str
