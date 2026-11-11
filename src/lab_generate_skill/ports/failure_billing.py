"""Reconcile original failure charges without a model/transport dependency.

Only complete error responses with an identified provider request and exact
charge qualify for this reader. Missing/unknown price or identity leaves the
shared dispatch fence closed; external read-only provider audit is separate.
Ledger RequestAuthority must verify authentic provider/request facts before any
charge commits. A typed result or error HTTP status alone is not that authority.
"""

from typing import Protocol
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_request import ModelSendPlan
from lab_generate_skill.domain.model_failure import FailureBillingResult


class FailureBilling(Protocol):
    def reconcile(
        self, plan: ModelSendPlan, transport_ref: EvidenceRef, op: OperationContext
    ) -> FailureBillingResult: ...
