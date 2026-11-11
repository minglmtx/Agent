"""Selected original preparation failure facts, never closure or retry authority.

The original resource/run journals and unknown read remain unchanged. A reader
must prove that no task or Actor work was dispatched and that the original
private instance cannot be reused before considering a separate stage grant.
"""

from typing import Literal, Self
from pydantic import model_validator
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .validation import Contract


class EndedPreparationStageEvidence(Contract):
    schema_version: Literal["ended-preparation-stage-evidence/1"] = (
        "ended-preparation-stage-evidence/1"
    )
    claim_ref: EvidenceRef
    source_ref: EvidenceRef
    run_ref: EvidenceRef
    actor_resource_ref: EvidenceRef
    site_resource_ref: EvidenceRef
    session_ref: EvidenceRef
    member_ref: EvidenceRef
    accounting_ref: EvidenceRef
    site_disposition_ref: EvidenceRef
    process_observation_ref: EvidenceRef | None = None

    @model_validator(mode="after")
    def exact_private_inputs(self) -> Self:
        for reference, schema in (
            (self.claim_ref, "source-claim/1"),
            (self.source_ref, "execution-task-source/2"),
            (self.run_ref, "run-journal-snapshot/2"),
            (self.actor_resource_ref, "resource-record/2"),
            (self.site_resource_ref, "resource-record/2"),
            (self.session_ref, "evidence-session-snapshot/3"),
            (self.member_ref, "retained-owned-member-result/1"),
            (self.accounting_ref, "slurm-accounting-raw/1"),
            (self.site_disposition_ref, "claimed-site-disposition/1"),
        ):
            private_state_ref(reference, schema)
        if self.process_observation_ref is not None:
            private_state_ref(
                self.process_observation_ref, "held-terminal-process-readback/1"
            )
        return self
