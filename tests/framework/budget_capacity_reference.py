"""Frozen pre-optimization capacity algorithm, test/measurement oracle only.

Intentionally reconstructs every prefix. Never install this as a production
fallback. State validity still uses the one public BudgetSnapshot contract.
"""

from lab_generate_skill.domain.budget_journal import (
    BudgetJournalSnapshot,
    settlement_slots,
)
from lab_generate_skill.domain.errors import JournalCapacityExceeded
from lab_generate_skill.domain.request_ledger import (
    BudgetSnapshot,
    ReserveEntry,
    DispatchEntry,
)
from lab_generate_skill.domain.generation import RequestRecord, RequestEvent


def reference_capacity(snapshot: BudgetJournalSnapshot) -> None:
    entries = snapshot.history.entries
    shell = snapshot.model_copy(
        update={
            "history": BudgetSnapshot(authorization=snapshot.history.authorization),
            "operations": (),
        }
    )
    size = len(shell.model_dump_json().encode())
    capacity = snapshot.capacity
    if (
        size + capacity.max_requests * 4 * (capacity.max_entry_bytes + 2)
        > capacity.max_bytes
    ):
        raise JournalCapacityExceeded("Frozen budget envelope cannot fit normal batch")
    for index, (entry, op) in enumerate(zip(entries, snapshot.operations), start=1):
        pair_bytes = (
            len(entry.model_dump_json().encode())
            + len(op.model_dump_json().encode())
            + 3
        )
        if pair_bytes > capacity.max_entry_bytes:
            raise JournalCapacityExceeded("Budget entry exceeds its frozen bound")
        size += pair_bytes - 3 + (2 if index > 1 else 0)
        prefix = BudgetSnapshot(
            authorization=snapshot.history.authorization, entries=entries[:index]
        )
        records = reference_projection(prefix)
        if len(records) > capacity.max_requests:
            raise JournalCapacityExceeded("Budget journal request count exhausted")
        reserve = settlement_slots(records)
        if index + reserve > capacity.max_entries:
            raise JournalCapacityExceeded("Budget entry would consume settlement slots")
        if size + reserve * (capacity.max_entry_bytes + 2) > capacity.max_bytes:
            raise JournalCapacityExceeded("Budget entry would consume settlement bytes")


def reference_projection(snapshot: BudgetSnapshot) -> tuple[RequestRecord, ...]:
    """Retained financial replay using full sums, independent of BudgetUsage."""
    records: dict[str, RequestRecord] = {}
    logical_keys: set[str] = set()
    operations: set[tuple[str, str, str]] = set()

    def usage(budget: str | None = None) -> int:
        return sum(
            r.held.units + r.charged.units
            for r in records.values()
            if budget is None or r.reservation.scope.budget_id == budget
        )

    def blocked() -> bool:
        return (
            any(r.exceeded_reservation for r in records.values())
            or usage() > snapshot.authorization.ceiling.units
            or any(
                usage(limit.budget_id) > limit.ceiling.units
                for limit in snapshot.authorization.budgets
            )
        )

    for entry in snapshot.entries:
        if isinstance(entry, ReserveEntry):
            reservation = entry.reservation
            request = reservation.request
            if reservation.scope.authorization != snapshot.authorization:
                raise ValueError("Reservation must retain the frozen authorization")
            if request.request_id in records:
                raise ValueError("A request can reserve only once")
            if request.logical_key in logical_keys:
                raise ValueError("Logical call already has a different request ID")
            logical_keys.add(request.logical_key)
            if (
                blocked()
                or usage() + reservation.ceiling.units
                > snapshot.authorization.ceiling.units
                or usage(request.budget_id) + reservation.ceiling.units
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
                raise ValueError("Request must reserve before dispatch or settlement")
            before = records[request_id]
            request = before.reservation.request
            if isinstance(entry, DispatchEntry):
                if blocked():
                    raise ValueError("Budget incident blocks further dispatch")
                event = RequestEvent(
                    operation_id=entry.operation_id, state="dispatching"
                )
            else:
                proof = entry.proof
                if proof.request != request:
                    raise ValueError("Proof must bind the complete original request")
                event = RequestEvent(
                    operation_id=entry.operation_id,
                    state=(
                        before.state
                        if proof.outcome == "charge_corrected"
                        else proof.outcome
                    ),
                    proof=proof,
                )
            record = RequestRecord(
                reservation=before.reservation, events=(*before.events, event)
            )
        key = (request.owner.run_id, request.owner.owner_id, entry.operation_id)
        if key in operations:
            raise ValueError("Operation ID cannot be reused within the same run/owner")
        operations.add(key)
        records[request.request_id] = record
    return tuple(records.values())
