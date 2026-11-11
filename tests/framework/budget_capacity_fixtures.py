"""Small synthetic histories; no real grants or external paid requests."""

from datetime import datetime, timedelta, timezone
from lab_generate_skill.domain.budget import (
    BudgetAuthorization,
    BudgetLimit,
    BudgetScope,
    Money,
)
from lab_generate_skill.domain.budget_journal import (
    BudgetJournalCapacity,
    BudgetJournalSnapshot,
)
from lab_generate_skill.domain.budget_policy import BudgetDispatchPolicy
from lab_generate_skill.domain.generation import Reservation, OutcomeProof
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.request_ledger import (
    BudgetSnapshot,
    BudgetEntry,
    ReserveEntry,
    DispatchEntry,
    OutcomeEntry,
)
from test_request_budget import request, ref, proof


def snapshot(count: int, outcomes: tuple[str, ...] = ()) -> BudgetJournalSnapshot:
    """Reserve distinct requests, optionally dispatch/settle the last one."""
    auth = BudgetAuthorization(
        authorization_id="authorization",
        authorization_ref=ref(),
        ceiling=Money(units=1000000),
        budgets=(BudgetLimit(budget_id="a", ceiling=Money(units=1000000)),),
    )
    scope = BudgetScope(authorization=auth, budget_id="a")
    entries: list[BudgetEntry] = []
    for index in range(count):
        identity = request("item-" + str(index))
        entries.append(
            ReserveEntry(
                operation_id="reserve-" + str(index),
                reservation=Reservation(
                    scope=scope, request=identity, ceiling=Money(units=4)
                ),
            )
        )
    if outcomes:
        if count == 0:
            raise ValueError("Outcomes need a request")
        identity = request("item-" + str(count - 1))
        if outcomes[0] != "released_not_dispatched":
            entries.append(
                DispatchEntry(operation_id="dispatch", request_id=identity.request_id)
            )
        previous: OutcomeProof | None = None
        for index, outcome in enumerate(outcomes):
            if outcome == "charge_corrected":
                assert previous is not None
                fact = OutcomeProof(
                    request=identity,
                    outcome="charge_corrected",
                    evidence=(ref("e"),),
                    charge=Money(units=index + 1),
                    supersedes=previous.digest,
                )
            else:
                fact = proof(identity, outcome, evidence=ref("abcdef"[index % 6]))
            entries.append(
                OutcomeEntry(operation_id="outcome-" + str(index), proof=fact)
            )
            previous = fact
    operations: list[OperationContext] = []
    for entry in entries:
        releasing = (
            isinstance(entry, OutcomeEntry)
            and entry.proof.outcome == "released_not_dispatched"
        )
        operations.append(
            OperationContext(
                operation_id=entry.operation_id,
                run_id="run",
                owner_id="owner",
                deadline=datetime.now(timezone.utc) + timedelta(hours=1),
                mode="cleanup" if releasing else "execute",
                parent_operation_id="original" if releasing else None,
            )
        )
    return BudgetJournalSnapshot(
        capacity=BudgetJournalCapacity(
            max_requests=max(count + 1, 2),
            max_entries=max(4 * (count + 1), len(entries) + 4, 8),
            max_bytes=8 * 1024 * 1024,
            max_entry_bytes=4096,
        ),
        dispatch_policy=BudgetDispatchPolicy(max_unsettled_dispatches=1),
        history=BudgetSnapshot(authorization=auth, entries=tuple(entries)),
        operations=tuple(operations),
    )
