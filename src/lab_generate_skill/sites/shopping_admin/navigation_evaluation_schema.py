"""Pure selected terminal evidence; source and resource rights remain external."""

from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import StateScope, private_state_ref


class AdminNavigationEvidence(Contract):
    schema_version: Literal["admin-navigation-evidence/1"] = (
        "admin-navigation-evidence/1"
    )
    scope: StateScope
    browser_spec_ref: EvidenceRef
    trace_ref: EvidenceRef | None
    page_intent_ref: EvidenceRef | None
    page_result_ref: EvidenceRef | None

    @model_validator(mode="after")
    def references(self) -> Self:
        for ref, schema in (
            (self.browser_spec_ref, "browser-resource-spec/4"),
            (self.trace_ref, "interaction-trace/1"),
            (self.page_intent_ref, "browser-capture-intent/1"),
            (self.page_result_ref, "browser-capture-result/1"),
        ):
            if ref is not None:
                private_state_ref(ref, schema)
                if ref.media_type != "application/json":
                    raise ValueError("Original private terminal JSON required")
        return self

    def evidence_refs(self) -> tuple[EvidenceRef, ...]:
        return tuple(
            ref
            for ref in (
                self.browser_spec_ref,
                self.trace_ref,
                self.page_intent_ref,
                self.page_result_ref,
            )
            if ref is not None
        )
