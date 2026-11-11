"""Original initial/Actor/page selections and closed-browser guard references."""

from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.initial_observation import InitialObservationSelection


class AdminNavigationTerminalSelection(Contract):
    schema_version: Literal["admin-navigation-terminal-selection/1"] = (
        "admin-navigation-terminal-selection/1"
    )
    scope: StateScope
    initial: InitialObservationSelection
    initial_checks_ref: EvidenceRef
    initial_capture_intent_ref: EvidenceRef
    initial_capture_result_ref: EvidenceRef
    trace_ref: EvidenceRef
    trace_snapshot_ref: EvidenceRef
    terminal_return_ref: EvidenceRef
    page_intent_ref: EvidenceRef
    page_result_ref: EvidenceRef
    prepare_request_ref: EvidenceRef
    environment_selection_ref: EvidenceRef

    @model_validator(mode="after")
    def originals(self) -> Self:
        for ref, schema in (
            (self.initial_checks_ref, "initial-state-checks/1"),
            (self.initial_capture_intent_ref, "browser-capture-intent/1"),
            (self.initial_capture_result_ref, "browser-capture-result/1"),
            (self.trace_ref, "interaction-trace/1"),
            (self.trace_snapshot_ref, "trace-journal-snapshot/1"),
            (self.page_intent_ref, "browser-capture-intent/1"),
            (self.page_result_ref, "browser-capture-result/1"),
            (self.prepare_request_ref, "site-task-request/2"),
            (self.environment_selection_ref, "environment-selection/1"),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json" or ref.size_bytes == 0:
                raise ValueError("Original nonempty private navigation JSON required")
        if self.terminal_return_ref.content_schema not in (
            "browser-initial-return/1",
            "browser-step-return/1",
        ):
            raise ValueError("Original navigation browser return required")
        private_state_ref(
            self.terminal_return_ref, self.terminal_return_ref.content_schema
        )
        return self


class AdminNavigationCapturedEvidence(Contract):
    schema_version: Literal["admin-navigation-captured-evidence/1"] = (
        "admin-navigation-captured-evidence/1"
    )
    scope: StateScope
    terminal_ref: EvidenceRef
    browser_closure_ref: EvidenceRef
    guard_intent_ref: EvidenceRef
    guard_result_ref: EvidenceRef

    @model_validator(mode="after")
    def original(self) -> Self:
        for ref, schema in (
            (self.terminal_ref, "admin-navigation-terminal-selection/1"),
            (self.browser_closure_ref, "closure-receipt/1"),
            (self.guard_intent_ref, "site-capture-intent/2"),
            (self.guard_result_ref, "site-task-result/1"),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json" or ref.size_bytes == 0:
                raise ValueError(
                    "Original complete private navigation capture JSON required"
                )
        return self
