"""Paid execution boundaries. No public API accepts a caller-created permit."""

from typing import Protocol
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_request import ModelSendPlan, ResolvedModelRequest
from lab_generate_skill.domain.model_response import ModelSendResult, ProviderReply


class ModelTransport(Protocol):
    """Trusted backend: one invocation, no retries, bounded I/O and response bytes.

    Use only the resolved role input and parameters as provider payload. Identity,
    operations and limits are routing/control, never model-visible message data.
    Credentials remain backend-owned memory. Return original response bytes and
    exact nanodollar charge or None, not rounded/estimated cost. Local inference
    has a separate future port; it must not fabricate paid budget records.
    """

    def validate(self, request: ResolvedModelRequest, op: OperationContext) -> None:
        """Bounded preflight of wire/config without network or other side effects."""
        ...

    def send(
        self, request: ResolvedModelRequest, op: OperationContext
    ) -> ProviderReply: ...


class ModelSendAuthority(Protocol):
    """Required live gate; no default allow. No provider call or mutation here.

    Verify actual plan/model parameters and role projection, provider/transport
    compatibility and bounded no-retry configuration, original writer/claim,
    current execution/trace intent, exclusivity and response storage capacity.
    Typed refs alone do not prove any of these. RequestLedger independently
    verifies shared budget dispatch and original provider settlement evidence.
    """

    def verify(self, plan: ModelSendPlan, request: ResolvedModelRequest) -> None: ...


class PaidModelSender(Protocol):
    def generate(self, plan: ModelSendPlan) -> ModelSendResult: ...
    def reconcile(
        self, plan: ModelSendPlan, fact_ref: EvidenceRef, op: OperationContext
    ) -> ModelSendResult: ...
