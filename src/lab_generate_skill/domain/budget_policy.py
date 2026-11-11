"""Frozen shared dispatch concurrency policy, distinct from storage capacity.

A committed dispatch is also a durable spending fence. Until its price/outcome
is verified terminal, no new reservation or different dispatch can proceed in
this authorization. This covers crashes before failure diagnostics are written.
No default policy is inferred for older plans or budget snapshots.
"""

from typing import Literal
from pydantic import Field
from .validation import Contract
from .request_ledger import BudgetSnapshot


class BudgetDispatchPolicy(Contract):
    schema_version: Literal["budget-dispatch-policy/1"] = "budget-dispatch-policy/1"
    max_unsettled_dispatches: int = Field(ge=1, le=1)


def unsettled_dispatches(history: BudgetSnapshot) -> tuple[str, ...]:
    return tuple(
        record.reservation.request.request_id
        for record in history.project()
        if record.state in ("dispatching", "uncertain")
    )
