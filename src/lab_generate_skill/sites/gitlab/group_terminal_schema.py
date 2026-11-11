"""Original Group initial/trace/page and closed-browser native selections."""

from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import StateScope, private_state_ref
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.task_execution import InitializedTask
from .evidence_schema import GitlabSiteCapture, GitlabPageCapture


class GroupTerminalSelection(Contract):
    schema_version: Literal["gitlab-group-terminal-selection/1"] = (
        "gitlab-group-terminal-selection/1"
    )
    scope: StateScope
    initialization_plan_ref: EvidenceRef
    capture_plan_ref: EvidenceRef
    initialized: InitializedTask
    initial: InitialObservationSelection
    initial_checks_ref: EvidenceRef
    initial_page: GitlabPageCapture
    before: GitlabSiteCapture
    trace_ref: EvidenceRef
    trace_snapshot_ref: EvidenceRef
    terminal_return_ref: EvidenceRef
    page: GitlabPageCapture
    prepare_request_ref: EvidenceRef
    environment_selection_ref: EvidenceRef

    @model_validator(mode="after")
    def refs(self) -> Self:
        for ref, schema in (
            (self.initialization_plan_ref, "task-initialization-plan/2"),
            (
                self.capture_plan_ref,
                (
                    "task-capture-plan/2"
                    if self.capture_plan_ref.content_schema == "task-capture-plan/2"
                    else "task-capture-plan/1"
                ),
            ),
            (self.initial_checks_ref, "initial-state-checks/1"),
            (self.trace_ref, "interaction-trace/1"),
            (self.trace_snapshot_ref, "trace-journal-snapshot/1"),
            (self.prepare_request_ref, "site-task-request/2"),
            (self.environment_selection_ref, "environment-selection/1"),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json" or ref.size_bytes == 0:
                raise ValueError("Complete original Group private JSON required")
        if self.terminal_return_ref.content_schema not in (
            "browser-initial-return/1",
            "browser-step-return/1",
        ):
            raise ValueError("Original Group terminal return required")
        private_state_ref(
            self.terminal_return_ref, self.terminal_return_ref.content_schema
        )
        return self


class GroupCapturedSelection(Contract):
    schema_version: Literal["gitlab-group-captured-selection/1"] = (
        "gitlab-group-captured-selection/1"
    )
    scope: StateScope
    terminal_ref: EvidenceRef
    browser_closure_ref: EvidenceRef
    browser_record_ref: EvidenceRef
    after: GitlabSiteCapture

    @model_validator(mode="after")
    def refs(self) -> Self:
        private_state_ref(self.terminal_ref, "gitlab-group-terminal-selection/1")
        private_state_ref(self.browser_closure_ref, "closure-receipt/1")
        private_state_ref(self.browser_record_ref, "resource-record/2")
        for ref in (
            self.terminal_ref,
            self.browser_closure_ref,
            self.browser_record_ref,
        ):
            if ref.media_type != "application/json" or ref.size_bytes == 0:
                raise ValueError("Complete original Group captured JSON required")
        return self
