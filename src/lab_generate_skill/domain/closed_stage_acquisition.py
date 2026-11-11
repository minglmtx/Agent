"""Explicit retained evidence for a failed stage before native registration."""

from typing import Literal, Self
from pydantic import model_validator
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .validation import Contract


class ClosedPreRegistrationStageEvidence(Contract):
    schema_version: Literal["closed-pre-registration-stage-evidence/1"] = (
        "closed-pre-registration-stage-evidence/1"
    )
    claim_ref: EvidenceRef
    source_ref: EvidenceRef
    run_ref: EvidenceRef
    actor_resource_ref: EvidenceRef
    session_ref: EvidenceRef
    diagnostic_ref: EvidenceRef
    accounting_ref: EvidenceRef
    site_spec_ref: EvidenceRef
    site_adapter_ref: EvidenceRef
    traceback_ref: EvidenceRef
    member_ref: EvidenceRef

    @model_validator(mode="after")
    def exact_evidence(self) -> Self:
        for reference, schema in (
            (self.claim_ref, "source-claim/1"),
            (self.source_ref, "execution-task-source/2"),
            (self.run_ref, "run-journal-snapshot/2"),
            (self.actor_resource_ref, "resource-record/2"),
            (self.session_ref, "evidence-session-snapshot/3"),
            (self.diagnostic_ref, "current-run-close/1"),
            (self.accounting_ref, "slurm-accounting-raw/1"),
            (self.site_spec_ref, "site-resource-spec/1"),
            (self.site_adapter_ref, "retained-python-source/1"),
            (self.traceback_ref, "retained-error-traceback/1"),
            (self.member_ref, "retained-owned-member-result/1"),
        ):
            private_state_ref(reference, schema)
        return self
