"""Actual frozen-plan membership and exact source-claim CAS transport.

No directory discovery, legacy claim fallback or writer permission is inferred
here. Actual caller/history authority is mandatory at the ledger boundary.
"""

from lab_generate_skill.ports.lifecycle import OperationControl

from lab_generate_skill.domain.claims import (
    SourceClaimBinding,
    SourceClaimRecord,
    SourceClaimReceipt,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.run_plan import RunPlans

MAX_CLAIM_BYTES = 128 * 1024


class ClaimEvidence:
    def __init__(self, store: EvidenceStore, plans: RunPlans) -> None:
        self._store, self._plans = store, plans

    def plan(self, binding: SourceClaimBinding, op: OperationContext) -> RunPlan:
        plan = RunPlan.model_validate(self._plans.load(binding.run, op))
        plan.check_binding(binding.run)
        if binding.task not in plan.tasks:
            raise OwnershipConflict(
                "Claim must match the complete original task in RunPlan"
            )
        return plan

    def publish(
        self, record: SourceClaimRecord, control: OperationControl
    ) -> EvidenceRef:
        return self._store.put(
            record.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="source-claim/1",
                visibility="private",
                producer="source-claims-v1",
            ),
            control=control,
        )

    def load(
        self, reference: EvidenceRef, control: OperationControl
    ) -> SourceClaimRecord:
        reference = EvidenceRef.model_validate(reference)
        private_state_ref(reference, "source-claim/1")
        if reference.size_bytes > MAX_CLAIM_BYTES:
            raise ValueError("Claim evidence exceeds its bounded record limit")
        record = SourceClaimRecord.model_validate_json(
            self._store.read(reference, control=control)
        )
        SourceClaimReceipt(record=record, reference=reference)
        return record
