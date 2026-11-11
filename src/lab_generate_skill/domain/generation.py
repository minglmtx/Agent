"""Paid-request identities, immutable reservations and append-only outcomes.

No model is called and no send permit is issued by these pure contracts.
Outcome proofs retain raw response/evidence identities. Their truth and stored
bytes must be checked by the ledger/provider adapter and independent reviewer.
"""

import hashlib
import json
from typing import Literal, Self

from pydantic import Field, model_validator

from .budget import BudgetScope, Money
from .evidence import EvidenceRef
from .identity import TaskIdentity
from .lifecycle import ResourceOwner
from .validation import Contract, Identifier, NonEmptyText, Sha256

RequestState = Literal[
    "budget_reserved",
    "dispatching",
    "uncertain",
    "succeeded",
    "charged_failure",
    "rejected_before_execution",
    "released_not_dispatched",
]


class RequestIdentity(Contract):
    schema_version: Literal["request-identity/1"] = "request-identity/1"
    request_id: Identifier
    authorization_id: Identifier
    budget_id: Identifier
    owner: ResourceOwner
    task: TaskIdentity
    attempt_id: Identifier | None = None
    candidate_index: int = Field(ge=0)
    revision_index: int = Field(ge=0)
    role: Literal["generator", "actor", "teacher"]
    logical_index: int = Field(ge=0)
    provider_id: Identifier
    model_id: NonEmptyText
    input_sha256: Sha256
    parameters_sha256: Sha256

    @property
    def logical_key(self) -> str:
        """One planned call cannot gain a second ID by changing worker or payload.

        Different authorized runs have distinct logical namespaces. Original
        claims and recovery authorization prevent retrying an old experiment in
        a new run; this identifier is not a replacement for those controls.
        """
        payload = [
            self.owner.run_id,
            self.task.model_dump(mode="json"),
            self.attempt_id,
            self.candidate_index,
            self.revision_index,
            self.role,
            self.logical_index,
        ]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class Reservation(Contract):
    """Same request identity and ceiling must always yield the same reservation."""

    schema_version: Literal["reservation/1"] = "reservation/1"
    scope: BudgetScope
    request: RequestIdentity
    ceiling: Money

    @model_validator(mode="after")
    def matching_scope(self) -> Self:
        if (
            self.request.authorization_id != self.scope.authorization.authorization_id
            or self.request.budget_id != self.scope.budget_id
        ):
            raise ValueError("Request must belong to the exact shared budget scope")
        if self.ceiling.units <= 0:
            raise ValueError(
                "Paid requests require a positive conservative reservation"
            )
        if self.ceiling.units > self.scope.ceiling.units:
            raise ValueError("Reservation exceeds its subbudget ceiling")
        return self


class DispatchPermit(Contract):
    """Identity of a committed dispatch, not a bearer authorization by construction.

    Only the durable ledger may return this to its one successful sender. The
    request adapter must consume that returned instance once and disable retries.
    A serialized copy, journal lookup or repeated dispatch call is not permission.
    """

    schema_version: Literal["dispatch-permit/1"] = "dispatch-permit/1"
    request: RequestIdentity
    dispatch_operation_id: Identifier
    request_revision: int = Field(ge=1)


class OutcomeProof(Contract):
    """Canonical proof digest gives settlement idempotency without self-hashing refs.

    uncertain may retain a saved response whose price is still unknown. Billing
    corrections append a new evidenced amount and explicitly supersede the last
    proof digest, preserving the execution outcome and all previous facts.
    """

    schema_version: Literal["request-outcome/2"] = "request-outcome/2"
    request: RequestIdentity
    outcome: Literal[
        "succeeded",
        "charged_failure",
        "rejected_before_execution",
        "released_not_dispatched",
        "uncertain",
        "charge_corrected",
    ]
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)
    response_ref: EvidenceRef | None = None
    provider_request_id: NonEmptyText | None = None
    charge: Money | None = None
    writer_termination_ref: EvidenceRef | None = None
    supersedes: Sha256 | None = None

    @model_validator(mode="after")
    def evidence_shape(self) -> Self:
        if self.response_ref is not None and self.provider_request_id is None:
            raise ValueError("Saved response must identify the provider request")
        if self.outcome in ("succeeded", "charged_failure"):
            if self.response_ref is None or self.charge is None:
                raise ValueError(
                    "Charged settlement requires saved response and exact charge"
                )
        elif self.outcome == "uncertain":
            if self.charge is not None:
                raise ValueError("Uncertain charge cannot be treated as a known cost")
        elif self.outcome in ("rejected_before_execution", "released_not_dispatched"):
            if (
                self.charge is None
                or self.charge.units != 0
                or self.response_ref is not None
            ):
                raise ValueError(
                    "Non-execution proof has no completed response and zero initial charge"
                )
            if (
                self.outcome == "released_not_dispatched"
                and self.writer_termination_ref is None
            ):
                raise ValueError(
                    "Release requires original-writer termination evidence"
                )
        else:
            if (
                self.charge is None
                or self.supersedes is None
                or self.response_ref is not None
            ):
                raise ValueError(
                    "Billing correction needs charge and predecessor proof, not a new response"
                )
        if self.outcome != "charge_corrected" and self.supersedes is not None:
            raise ValueError("Only billing corrections replace an accounting amount")
        if (
            self.outcome != "released_not_dispatched"
            and self.writer_termination_ref is not None
        ):
            raise ValueError(
                "Writer termination alone is not proof of provider non-execution"
            )
        return self

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        return hashlib.sha256(raw).hexdigest()


class RequestEvent(Contract):
    schema_version: Literal["request-event/2"] = "request-event/2"
    operation_id: Identifier
    state: RequestState
    proof: OutcomeProof | None = None


class RequestRecord(Contract):
    schema_version: Literal["request-record/2"] = "request-record/2"
    reservation: Reservation
    events: tuple[RequestEvent, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def history(self) -> Self:
        first = self.events[0]
        if first.state != "budget_reserved" or first.proof is not None:
            raise ValueError("Request begins with one persisted reservation")
        operations = {first.operation_id}
        digests: set[str] = set()
        previous_proof: OutcomeProof | None = None
        for before, event in zip(self.events, self.events[1:]):
            if event.operation_id in operations:
                raise ValueError("Request operation IDs must be unique")
            operations.add(event.operation_id)
            proof = event.proof
            if event.state == "dispatching":
                if before.state != "budget_reserved" or proof is not None:
                    raise ValueError("A request may enter dispatching only once")
                continue
            if proof is None or proof.request != self.reservation.request:
                raise ValueError(
                    "Outcome must bind the complete original request identity"
                )
            if proof.digest in digests:
                raise ValueError("Repeated proof is a replay, not a new event")
            digests.add(proof.digest)
            if proof.outcome == "charge_corrected":
                if (
                    before.state
                    not in (
                        "succeeded",
                        "charged_failure",
                        "rejected_before_execution",
                        "released_not_dispatched",
                    )
                    or event.state != before.state
                    or previous_proof is None
                    or proof.supersedes != previous_proof.digest
                ):
                    raise ValueError(
                        "Billing correction must follow the current terminal accounting proof"
                    )
            else:
                allowed = {
                    "budget_reserved": {"released_not_dispatched"},
                    "dispatching": {
                        "uncertain",
                        "succeeded",
                        "charged_failure",
                        "rejected_before_execution",
                    },
                    "uncertain": {
                        "uncertain",
                        "succeeded",
                        "charged_failure",
                        "rejected_before_execution",
                    },
                }
                if event.state != proof.outcome or event.state not in allowed.get(
                    before.state, set()
                ):
                    raise ValueError("Outcome cannot authorize this request transition")
            previous_proof = proof
        return self

    @property
    def revision(self) -> int:
        return len(self.events) - 1

    @property
    def state(self) -> RequestState:
        return self.events[-1].state

    @property
    def charged(self) -> Money:
        for event in reversed(self.events):
            if event.proof is not None and event.proof.charge is not None:
                return event.proof.charge
        return Money(units=0)

    @property
    def held(self) -> Money:
        return (
            self.reservation.ceiling
            if self.state in ("budget_reserved", "dispatching", "uncertain")
            else Money(units=0)
        )

    @property
    def exceeded_reservation(self) -> bool:
        """An overage remains an incident even after a later refund/correction."""
        return any(
            event.proof is not None
            and event.proof.charge is not None
            and event.proof.charge.units > self.reservation.ceiling.units
            for event in self.events
        )


class RequestReceipt(Contract):
    """Committed record plus exact proof identity, never another send permit."""

    schema_version: Literal["request-receipt/2"] = "request-receipt/2"
    record: RequestRecord
    proof_sha256: Sha256

    @model_validator(mode="after")
    def proof_belongs_to_record(self) -> Self:
        if not any(
            event.proof is not None and event.proof.digest == self.proof_sha256
            for event in self.record.events
        ):
            raise ValueError(
                "Receipt must identify a proof actually retained in the record"
            )
        return self
