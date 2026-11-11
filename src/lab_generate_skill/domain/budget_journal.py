"""Bounded durable budget envelope: full operation lineage and settlement room.

Pure request transitions remain in request_ledger.py. This envelope freezes
storage capacity and keeps enough space for each pending request's first final
settlement, not an unlimited number of subsequent billing corrections. Verified
proofs that cannot be acknowledged remain in CAS for reconciliation.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from .errors import JournalCapacityExceeded
from .budget_policy import BudgetDispatchPolicy
from .evidence import EvidenceRef
from .generation import RequestRecord
from .lifecycle import OperationContext
from .request_ledger import BudgetSnapshot, DispatchEntry, OutcomeEntry, ReserveEntry
from .validation import Contract


class BudgetJournalCapacity(Contract):
    schema_version: Literal["budget-journal-capacity/1"] = "budget-journal-capacity/1"
    max_requests: int = Field(ge=1, le=2500)
    max_entries: int = Field(ge=4, le=10000)
    max_bytes: int = Field(ge=1, le=8 * 1024 * 1024)
    max_entry_bytes: int = Field(ge=1, le=8 * 1024 * 1024)

    @model_validator(mode="after")
    def normal_batch_fits(self) -> Self:
        if self.max_requests * 4 > self.max_entries:
            raise ValueError("Reserve/dispatch/uncertain/settle must fit the batch")
        if self.max_requests * 4 * (self.max_entry_bytes + 2) > self.max_bytes:
            raise ValueError("Batch worst-case entries exceed the byte budget")
        return self


def settlement_slots(records: tuple[RequestRecord, ...]) -> int:
    remaining = {"budget_reserved": 3, "dispatching": 2, "uncertain": 1}
    return sum(remaining.get(record.state, 0) for record in records)


class BudgetJournalSnapshot(Contract):
    schema_version: Literal["budget-journal-snapshot/2"] = "budget-journal-snapshot/2"
    capacity: BudgetJournalCapacity
    dispatch_policy: BudgetDispatchPolicy
    history: BudgetSnapshot
    operations: tuple[OperationContext, ...] = ()

    @model_validator(mode="after")
    def operation_lineage(self) -> Self:
        if len(self.operations) != len(self.history.entries):
            raise ValueError("Every budget entry needs its original operation")
        requests = {
            record.reservation.request.request_id: record.reservation.request
            for record in self.history.project()
        }
        unsettled: set[str] = set()
        for entry, op in zip(self.history.entries, self.operations):
            if isinstance(entry, (ReserveEntry, DispatchEntry)) and unsettled:
                raise ValueError("New spending crossed an unsettled dispatch fence")
            if isinstance(entry, ReserveEntry):
                request = entry.reservation.request
            elif isinstance(entry, DispatchEntry):
                request = requests[entry.request_id]
            else:
                request = entry.proof.request
            if isinstance(entry, DispatchEntry):
                unsettled.add(request.request_id)
            elif isinstance(entry, OutcomeEntry) and entry.proof.outcome != "uncertain":
                unsettled.discard(request.request_id)
            if (op.run_id, op.owner_id, op.attempt_id, op.operation_id) != (
                request.owner.run_id,
                request.owner.owner_id,
                request.attempt_id,
                entry.operation_id,
            ):
                raise ValueError(
                    "Budget entry must retain exact request operation scope"
                )
            releasing = (
                isinstance(entry, OutcomeEntry)
                and entry.proof.outcome == "released_not_dispatched"
            )
            if releasing and op.mode != "cleanup":
                raise ValueError("Undispatched release requires a cleanup operation")
            if (
                isinstance(entry, (ReserveEntry, DispatchEntry))
                and op.mode != "execute"
            ):
                raise ValueError("Cleanup cannot reserve or dispatch")
        return self

    def check_capacity(self) -> None:
        """Check every prefix in one replay; later small outcomes hide nothing.

        State transitions and historical money limits use BudgetSnapshot's
        shared replay. Only entry bytes and pending settlement slots accumulate
        here. No prefix snapshots, last-prefix shortcut or cross-call cache.
        """
        entries = self.history.entries
        if len(entries) != len(self.operations):
            raise ValueError("Every budget entry needs its original operation")
        shell = self.model_copy(
            update={
                "history": BudgetSnapshot(authorization=self.history.authorization),
                "operations": (),
            }
        )
        shell_bytes = len(shell.model_dump_json().encode())
        capacity = self.capacity
        if (
            shell_bytes + capacity.max_requests * 4 * (capacity.max_entry_bytes + 2)
            > capacity.max_bytes
        ):
            raise JournalCapacityExceeded(
                "Frozen budget envelope cannot fit normal batch"
            )
        size = shell_bytes
        slots: dict[str, int] = {}
        reserve = 0
        changes = self.history.replay_changes()
        for index, (entry, op, record) in enumerate(
            zip(entries, self.operations, changes, strict=True), start=1
        ):
            pair_bytes = (
                len(entry.model_dump_json().encode())
                + len(op.model_dump_json().encode())
                + 3
            )
            if pair_bytes > capacity.max_entry_bytes:
                raise JournalCapacityExceeded("Budget entry exceeds its frozen bound")
            size += pair_bytes - 3 + (2 if index > 1 else 0)
            request_id = record.reservation.request.request_id
            remaining = settlement_slots((record,))
            reserve += remaining - slots.get(request_id, 0)
            slots[request_id] = remaining
            if len(slots) > capacity.max_requests:
                raise JournalCapacityExceeded("Budget journal request count exhausted")
            if index + reserve > capacity.max_entries:
                raise JournalCapacityExceeded(
                    "Budget entry would consume settlement slots"
                )
            if size + reserve * (capacity.max_entry_bytes + 2) > capacity.max_bytes:
                raise JournalCapacityExceeded(
                    "Budget entry would consume settlement bytes"
                )


class SettlementPending(RuntimeError):
    """A verified proof is saved but ledger acknowledgement is unconfirmed.

    Inspect/replay this proof; never resend the paid request. The original commit
    failure, including any cleanup exception group, remains the explicit cause.
    """

    reason_code = "SETTLEMENT_COMMIT_UNCONFIRMED"

    def __init__(self, proof_ref: EvidenceRef) -> None:
        self.proof_ref = proof_ref
        super().__init__("Saved settlement proof requires ledger reconciliation")


class BudgetReconciliationRequired(RuntimeError):
    """Pending settlement evidence blocks NEW reservations and sends globally."""

    reason_code = "BUDGET_RECONCILIATION_REQUIRED"

    def __init__(self, message: str, request_ids: tuple[str, ...] = ()) -> None:
        self.request_ids = request_ids
        super().__init__(message)
