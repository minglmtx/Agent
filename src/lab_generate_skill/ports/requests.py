"""Shared authorization ledger contract; no provider implementation or retries.

reserve atomically accounts for confirmed cost plus ALL held reservations across
runs/workers. expected_revision is the per-request revision, not the global
ledger revision; the adapter serializes the shared authorization transaction.
mark_dispatching commits once before returning a one-time permit to its caller;
replay/lookup must never return another permit. A lost acknowledgement is
uncertain, even if the caller believes it has not sent. settle verifies stored
evidence and request binding before commit, retaining unknown charges/overages.
Recovery release also requires verified original-writer termination and proof
that no dispatch committed. Methods never invoke the provider themselves.

The frozen BudgetDispatchPolicy allows one unsettled dispatch per shared
authorization. dispatching/uncertain histories fence NEW reservations/sends,
including across runs/subbudgets and after a crash with no failure diagnostics.
Reads, exact replays and settlement remain available. charged_failure records a
verified original error response and exact charge; it never means model success
or permission to repeat that request. Old journal/plan versions are rejected.
"""

from typing import Protocol

from lab_generate_skill.domain.budget import BudgetScope, Money
from lab_generate_skill.domain.generation import (
    DispatchPermit,
    OutcomeProof,
    RequestIdentity,
    RequestReceipt,
    RequestRecord,
    Reservation,
)
from lab_generate_skill.domain.lifecycle import OperationContext


class RequestLedger(Protocol):
    def reserve(
        self,
        scope: BudgetScope,
        request: RequestIdentity,
        ceiling: Money,
        op: OperationContext,
    ) -> Reservation: ...
    def mark_dispatching(
        self, reservation: Reservation, expected_revision: int, op: OperationContext
    ) -> DispatchPermit: ...
    def settle(
        self,
        request: RequestIdentity,
        proof: OutcomeProof,
        expected_revision: int,
        op: OperationContext,
    ) -> RequestReceipt: ...
    def read(self, request: RequestIdentity, op: OperationContext) -> RequestRecord: ...


class RequestAuthority(Protocol):
    """Trusted local validation under the authorization transaction lock.

    Validate real user authority, immutable claim/request/input binding and the
    actual caller's writer incarnation; matching strings or typed refs alone are
    insufficient. Proof verification checks provider facts and, for undispatched
    release, original-writer/descendant termination and no committed dispatch.
    No provider call, submit or implicit retry is allowed in these hooks.
    """

    def authorize_reservation(
        self, reservation: Reservation, op: OperationContext
    ) -> None: ...

    def authorize_dispatch(
        self, record: RequestRecord, op: OperationContext
    ) -> None: ...

    def verify_outcome(
        self, record: RequestRecord, proof: OutcomeProof, op: OperationContext
    ) -> None: ...
