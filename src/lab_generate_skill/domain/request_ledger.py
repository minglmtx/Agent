"""Pure shared-budget event stream; durable adapters must commit it atomically.

Every reservation/state/accounting change shares one authorization history.
Replaying validates the historical budget at each reserve and dispatch, while
settlement always records evidenced charges, even above caps. No function here
returns a DispatchPermit or authorizes a real provider call.
"""

from typing import Annotated, Literal, Self
from collections.abc import Iterator

from pydantic import Field, TypeAdapter, model_validator

from .budget import BudgetAuthorization, BudgetScope, Money
from .budget_usage import BudgetUsage
from .errors import (
    BudgetExceeded,
    DispatchAlreadyCommitted,
    EvidenceNotFound,
    OwnershipConflict,
    RevisionConflict,
)
from .generation import (
    OutcomeProof,
    RequestEvent,
    RequestIdentity,
    RequestReceipt,
    RequestRecord,
    Reservation,
)
from .validation import Contract, Identifier


class ReserveEntry(Contract):
    schema_version: Literal["budget-reserve-entry/1"] = "budget-reserve-entry/1"
    kind: Literal["reserve"] = "reserve"
    operation_id: Identifier
    reservation: Reservation


class DispatchEntry(Contract):
    schema_version: Literal["budget-dispatch-entry/1"] = "budget-dispatch-entry/1"
    kind: Literal["dispatch"] = "dispatch"
    operation_id: Identifier
    request_id: Identifier


class OutcomeEntry(Contract):
    schema_version: Literal["budget-outcome-entry/2"] = "budget-outcome-entry/2"
    kind: Literal["outcome"] = "outcome"
    operation_id: Identifier
    proof: OutcomeProof


BudgetEntry = Annotated[
    ReserveEntry | DispatchEntry | OutcomeEntry, Field(discriminator="kind")
]


_ENTRY: TypeAdapter[BudgetEntry] = TypeAdapter(BudgetEntry)


def _usage(records: tuple[RequestRecord, ...], budget_id: str | None = None) -> int:
    return sum(
        record.charged.units + record.held.units
        for record in records
        if budget_id is None or record.reservation.scope.budget_id == budget_id
    )


def _blocked(
    authorization: BudgetAuthorization, records: tuple[RequestRecord, ...]
) -> bool:
    usage = BudgetUsage(authorization)
    for record in records:
        usage.replace(None, record)
    return usage.blocked


class BudgetSnapshot(Contract):
    """All runs/workers in an authorization share this one factual history."""

    schema_version: Literal["request-budget-snapshot/2"] = "request-budget-snapshot/2"
    authorization: BudgetAuthorization
    entries: tuple[BudgetEntry, ...] = Field(default=(), max_length=10000)

    def replay_changes(self) -> Iterator[RequestRecord]:
        """Yield the changed record after each validated entry, in commit order.

        Consumers must exhaust this iterator before accepting a whole history.
        This is the sole replay implementation shared with capacity accounting;
        it carries no cached authority or mutable state between invocations.
        """
        authorization = BudgetAuthorization.model_validate(self.authorization)
        usage = BudgetUsage(authorization)
        records: dict[str, RequestRecord] = {}
        logical_keys: set[str] = set()
        operations: set[tuple[str, str, str]] = set()
        for raw_entry in self.entries:
            entry = _ENTRY.validate_python(raw_entry, strict=True)
            if isinstance(entry, ReserveEntry):
                reservation = entry.reservation
                request = reservation.request
                if reservation.scope.authorization != authorization:
                    raise ValueError("Reservation must retain the frozen authorization")
                if request.request_id in records:
                    raise ValueError("A request can reserve only once")
                if request.logical_key in logical_keys:
                    raise ValueError("Logical call already has a different request ID")
                logical_keys.add(request.logical_key)
                if (
                    usage.blocked
                    or usage.total + reservation.ceiling.units
                    > authorization.ceiling.units
                    or usage.for_budget(request.budget_id) + reservation.ceiling.units
                    > reservation.scope.ceiling.units
                ):
                    raise ValueError(
                        "Reservation exceeded shared authorization or subbudget at commit"
                    )
                record = RequestRecord(
                    reservation=reservation,
                    events=(
                        RequestEvent(
                            operation_id=entry.operation_id, state="budget_reserved"
                        ),
                    ),
                )
            else:
                request_id = (
                    entry.request_id
                    if isinstance(entry, DispatchEntry)
                    else entry.proof.request.request_id
                )
                if request_id not in records:
                    raise ValueError(
                        "Request must reserve before dispatch or settlement"
                    )
                before = records[request_id]
                request = before.reservation.request
                if isinstance(entry, DispatchEntry):
                    if usage.blocked:
                        raise ValueError("Budget incident blocks further dispatch")
                    event = RequestEvent(
                        operation_id=entry.operation_id, state="dispatching"
                    )
                else:
                    proof = entry.proof
                    if proof.request != request:
                        raise ValueError(
                            "Proof must bind the complete original request"
                        )
                    state = (
                        before.state
                        if proof.outcome == "charge_corrected"
                        else proof.outcome
                    )
                    event = RequestEvent(
                        operation_id=entry.operation_id, state=state, proof=proof
                    )
                record = RequestRecord(
                    reservation=before.reservation, events=(*before.events, event)
                )
            key = (request.owner.run_id, request.owner.owner_id, entry.operation_id)
            if key in operations:
                raise ValueError(
                    "Operation ID cannot be reused within the same run/owner"
                )
            operations.add(key)
            usage.replace(records.get(request.request_id), record)
            records[request.request_id] = record
            yield record

    def project(self) -> tuple[RequestRecord, ...]:
        records: dict[str, RequestRecord] = {}
        for record in self.replay_changes():
            records[record.reservation.request.request_id] = record
        return tuple(records.values())

    @model_validator(mode="after")
    def historical_limits(self) -> Self:
        self.project()
        return self

    @property
    def revision(self) -> int:
        return len(self.entries)

    @property
    def blocked(self) -> bool:
        return _blocked(self.authorization, self.project())

    @property
    def charged(self) -> Money:
        return Money(units=sum(record.charged.units for record in self.project()))

    @property
    def held(self) -> Money:
        return Money(units=sum(record.held.units for record in self.project()))


def _record(snapshot: BudgetSnapshot, request: RequestIdentity) -> RequestRecord:
    for record in snapshot.project():
        if record.reservation.request.request_id == request.request_id:
            if record.reservation.request != request:
                raise OwnershipConflict(
                    "Request ID already binds different input, parameters or owner"
                )
            return record
    raise EvidenceNotFound("Request reservation is absent")


def _revision(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("Expected request revision must be a nonnegative integer")


def reserve_request(
    snapshot: BudgetSnapshot,
    scope: BudgetScope,
    request: RequestIdentity,
    ceiling: Money,
    operation_id: str,
) -> tuple[BudgetSnapshot, Reservation]:
    """Pure reserve; caller commits returned snapshot under an authorization lock."""
    reservation = Reservation(scope=scope, request=request, ceiling=ceiling)
    entry = ReserveEntry(operation_id=operation_id, reservation=reservation)
    if scope.authorization != snapshot.authorization:
        raise OwnershipConflict("Authorization cannot change during a request ledger")
    records = snapshot.project()
    for record in records:
        if record.reservation.request.request_id == request.request_id:
            if record.reservation != reservation:
                raise OwnershipConflict(
                    "Repeated reserve must retain request, scope and ceiling"
                )
            return snapshot, record.reservation
        if record.reservation.request.logical_key == request.logical_key:
            raise OwnershipConflict("Logical call cannot gain a second request ID")
    if (
        snapshot.blocked
        or _usage(records) + ceiling.units > snapshot.authorization.ceiling.units
        or _usage(records, scope.budget_id) + ceiling.units > scope.ceiling.units
    ):
        raise BudgetExceeded(
            "Shared authorization or subbudget cannot reserve this request"
        )
    return (
        BudgetSnapshot(
            authorization=snapshot.authorization, entries=(*snapshot.entries, entry)
        ),
        reservation,
    )


def dispatch_request(
    snapshot: BudgetSnapshot,
    reservation: Reservation,
    expected_revision: int,
    operation_id: str,
) -> BudgetSnapshot:
    """Pure dispatch transition only; repeated dispatch is never idempotent permission."""
    _revision(expected_revision)
    entry = DispatchEntry(
        operation_id=operation_id, request_id=reservation.request.request_id
    )
    record = _record(snapshot, reservation.request)
    if record.reservation != reservation:
        raise OwnershipConflict("Dispatch must use the original reservation")
    if record.state != "budget_reserved":
        raise DispatchAlreadyCommitted(
            "Request has already dispatched or closed; do not send again"
        )
    if record.revision != expected_revision:
        raise RevisionConflict("Request revision changed before dispatch")
    if snapshot.blocked:
        raise BudgetExceeded("Prior accounting incident blocks further sends")
    return BudgetSnapshot(
        authorization=snapshot.authorization, entries=(*snapshot.entries, entry)
    )


def settle_request(
    snapshot: BudgetSnapshot,
    request: RequestIdentity,
    proof: OutcomeProof,
    expected_revision: int,
    operation_id: str,
) -> tuple[BudgetSnapshot, RequestReceipt]:
    """Append facts, including overages; identical proof returns its original receipt."""
    _revision(expected_revision)
    entry = OutcomeEntry(operation_id=operation_id, proof=proof)
    record = _record(snapshot, request)
    if proof.request != request:
        raise OwnershipConflict("Outcome input and request identities do not agree")
    for index, event in enumerate(record.events):
        if event.proof is not None and event.proof.digest == proof.digest:
            original = RequestRecord(
                reservation=record.reservation, events=record.events[: index + 1]
            )
            return snapshot, RequestReceipt(record=original, proof_sha256=proof.digest)
    if record.revision != expected_revision:
        raise RevisionConflict("Request revision changed before settlement")
    updated = BudgetSnapshot(
        authorization=snapshot.authorization, entries=(*snapshot.entries, entry)
    )
    committed = _record(updated, request)
    return updated, RequestReceipt(record=committed, proof_sha256=proof.digest)
