"""Original category evidence selection; no page, permission or ready claims."""

from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from .evidence_schema import SiteCaptureEvidence, PageCaptureEvidence


class CategoryNavigationEvidence(Contract):
    schema_version: Literal["shopping-category-navigation-evidence/1"] = (
        "shopping-category-navigation-evidence/1"
    )
    environment_ref: EvidenceRef | None
    initial: InitialObservationSelection | None
    initial_checks_ref: EvidenceRef | None
    trace_ref: EvidenceRef | None
    trace_snapshot_ref: EvidenceRef | None
    terminal_return_ref: EvidenceRef | None
    page: PageCaptureEvidence | None
    final_guard: SiteCaptureEvidence | None
    browser_closure_ref: EvidenceRef | None

    @model_validator(mode="after")
    def original_refs(self) -> Self:
        for ref, schema in (
            (self.environment_ref, "environment-selection/1"),
            (self.initial_checks_ref, "initial-state-checks/1"),
            (self.trace_ref, "interaction-trace/1"),
            (self.trace_snapshot_ref, "trace-journal-snapshot/1"),
            (self.browser_closure_ref, "closure-receipt/1"),
        ):
            if ref is not None:
                private_state_ref(ref, schema)
                if ref.media_type != "application/json":
                    raise ValueError("Private category JSON evidence required")
        if self.terminal_return_ref is not None:
            private_state_ref(
                self.terminal_return_ref, self.terminal_return_ref.content_schema
            )
            if (
                self.terminal_return_ref.content_schema
                not in ("browser-initial-return/1", "browser-step-return/1")
                or self.terminal_return_ref.media_type != "application/json"
            ):
                raise ValueError("Original category terminal browser return required")
        return self

    def evidence_refs(self) -> tuple[EvidenceRef, ...]:
        return tuple(dict.fromkeys(evidence_references(self)))
