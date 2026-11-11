"""Selected original Map evidence references; large bodies stay in complete files."""

from typing import Literal, Self
from .navigation_evidence_schema import NavigationOutcome as NavigationOutcome
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from .tasks.overlay_spec import SOURCE as SOURCE


class MapCapturePair(Contract):
    intent_ref: EvidenceRef
    result_ref: EvidenceRef

    @model_validator(mode="after")
    def references(self) -> Self:
        schema = self.intent_ref.content_schema
        result = {
            "site-capture-intent/2": "site-task-result/1",
            "browser-capture-intent/1": "browser-capture-result/1",
        }
        if schema not in result:
            raise ValueError("Original site or browser capture pair required")
        private_state_ref(self.intent_ref, schema)
        private_state_ref(self.result_ref, result[schema])
        return self


class MapOverlayEvidence(Contract):
    schema_version: Literal["map-overlay-evidence/1"] = "map-overlay-evidence/1"
    environment_ref: EvidenceRef | None
    terminal_ref: EvidenceRef | None
    page: MapCapturePair | None
    references: tuple[MapCapturePair, ...] | None = Field(max_length=10000)
    final_guard: MapCapturePair | None
    browser_closure_ref: EvidenceRef | None
    trace_ref: EvidenceRef | None
    trace_snapshot_ref: EvidenceRef | None

    @model_validator(mode="after")
    def references_checked(self) -> Self:
        for ref, schema in (
            (self.environment_ref, "environment-selection/1"),
            (self.terminal_ref, "map-terminal-selection/1"),
            (self.browser_closure_ref, "closure-receipt/1"),
            (self.trace_ref, "interaction-trace/1"),
            (self.trace_snapshot_ref, "trace-journal-snapshot/1"),
        ):
            if ref is not None:
                private_state_ref(ref, schema)
        for pair in (
            *(self.references or ()),
            *((self.final_guard,) if self.final_guard else ()),
        ):
            if pair.intent_ref.content_schema != "site-capture-intent/2":
                raise ValueError("Original site capture required")
        if (
            self.page
            and self.page.intent_ref.content_schema != "browser-capture-intent/1"
        ):
            raise ValueError("Original browser health capture required")
        if self.references is not None and len(
            {p.intent_ref.sha256 for p in self.references}
        ) != len(self.references):
            raise ValueError("Duplicate original Map DB capture")
        return self

    def evidence_refs(self) -> tuple[EvidenceRef, ...]:
        refs = tuple(
            r
            for r in (
                self.environment_ref,
                self.terminal_ref,
                self.browser_closure_ref,
                self.trace_ref,
                self.trace_snapshot_ref,
            )
            if r is not None
        )
        pairs = (
            *(self.references or ()),
            *((self.page,) if self.page else ()),
            *((self.final_guard,) if self.final_guard else ()),
        )
        return refs + tuple(
            r for pair in pairs for r in (pair.intent_ref, pair.result_ref)
        )


class MapNavigationEvidence(Contract):
    """Original outer judgment references; the terminal owns capture and trace."""

    schema_version: Literal["map-navigation-evidence/1"] = "map-navigation-evidence/1"
    environment_ref: EvidenceRef | None
    terminal_ref: EvidenceRef | None
    final_guard: MapCapturePair | None
    browser_closure_ref: EvidenceRef | None

    @model_validator(mode="after")
    def originals(self) -> Self:
        for ref, schema in (
            (self.environment_ref, "environment-selection/1"),
            (self.terminal_ref, "map-navigation-terminal-selection/1"),
            (self.browser_closure_ref, "closure-receipt/1"),
        ):
            if ref is not None:
                private_state_ref(ref, schema)
        if (
            self.final_guard is not None
            and self.final_guard.intent_ref.content_schema != "site-capture-intent/2"
        ):
            raise ValueError("Original complete site guard required")
        return self

    def evidence_refs(self) -> tuple[EvidenceRef, ...]:
        refs = tuple(
            r
            for r in (self.environment_ref, self.terminal_ref, self.browser_closure_ref)
            if r is not None
        )
        return refs + (
            (self.final_guard.intent_ref, self.final_guard.result_ref)
            if self.final_guard is not None
            else ()
        )
