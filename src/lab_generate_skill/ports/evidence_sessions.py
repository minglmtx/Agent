"""Durable evidence-session admission: implement inside supervised persistence.

Binding/namespace/capacity are immutable. The configured root and authority must
prevent aliases/new session IDs bypassing pending original scope. A constructor
or parsed snapshot is not admission; begin commits before effects and exact
replay raises DispatchAlreadyCommitted. Unknown commit never authorizes retry.
An implementation must not introduce unbounded parent-process filesystem I/O.
"""

from typing import Protocol
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceSessionCapacity,
    EvidenceOperationIntent,
    EvidenceOperationOutcome,
    EvidenceSessionResolution,
)
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot


class EvidenceSessionAuthority(Protocol):
    """Mandatory real checks; no default unit/no-op authority in production.

    Bind exact configured physical storage, explicit run/source scope, owner, release and
    command. Validate actual worker incarnation/outcome and independent original
    worker termination, object identity/absence and owned-temporary cleanup.
    Typed facts, PID absence, lease age or a zero exit code alone are insufficient.
    Run scope is for approved run/plan/resource evidence before a source claim
    exists; it grants no source execution rights. Source scope additionally
    requires the original source ownership. No fabricated source IDs or implicit
    source-to-run fallback; root and scope come from trusted bootstrap.
    """

    def authorize_binding(
        self, binding: EvidenceSessionBinding, op: OperationContext
    ) -> None: ...
    def authorize_intent(
        self, binding: EvidenceSessionBinding, intent: EvidenceOperationIntent
    ) -> None: ...
    def verify_outcome(
        self,
        binding: EvidenceSessionBinding,
        intent: EvidenceOperationIntent,
        outcome: EvidenceOperationOutcome,
        op: OperationContext,
    ) -> None: ...
    def verify_resolution(
        self,
        binding: EvidenceSessionBinding,
        intent: EvidenceOperationIntent,
        resolution: EvidenceSessionResolution,
    ) -> None: ...


class EvidenceSessions(Protocol):
    """Only original stored facts survive restart; reads never redo original I/O.

    Used/missing/corrupt namespace fails closed, never empty initialization.
    create replays only the exact binding/capacity. Resolution requires its own
    bounded parent-linked cleanup, never executes the original read/put again.
    Terminal records remain; original source and shared-resource stop scopes are
    enforced independently from the paid-request concurrency limit (still1).
    """

    def create(
        self,
        binding: EvidenceSessionBinding,
        capacity: EvidenceSessionCapacity,
        op: OperationContext,
    ) -> EvidenceSessionSnapshot: ...
    def read(
        self, binding: EvidenceSessionBinding, op: OperationContext
    ) -> EvidenceSessionSnapshot: ...
    def begin(
        self,
        binding: EvidenceSessionBinding,
        intent: EvidenceOperationIntent,
        expected_revision: int,
    ) -> EvidenceSessionSnapshot: ...
    def record_outcome(
        self,
        binding: EvidenceSessionBinding,
        outcome: EvidenceOperationOutcome,
        expected_revision: int,
        op: OperationContext,
    ) -> EvidenceSessionSnapshot: ...
    def resolve(
        self,
        binding: EvidenceSessionBinding,
        resolution: EvidenceSessionResolution,
        expected_revision: int,
    ) -> EvidenceSessionSnapshot: ...
