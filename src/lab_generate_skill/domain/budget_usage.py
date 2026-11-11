"""Replay-local exact accounting, not a cache or an authorization mechanism.

Input: validated records from the single budget transition implementation.
replace consumes one prior/current version of the SAME request; it maintains
total/subbudget usage and sticky reservation incidents. No history is accepted
by this helper alone, no I/O occurs, and instances never cross replay calls.
"""

from .budget import BudgetAuthorization
from .generation import RequestRecord


class BudgetUsage:
    def __init__(self, authorization: BudgetAuthorization) -> None:
        self._authorization = authorization
        self._ceiling = authorization.ceiling.units
        self._limits = {
            item.budget_id: item.ceiling.units for item in authorization.budgets
        }
        self._used: dict[str, int] = {}
        self._total = 0
        self._overdrawn: set[str] = set()
        self._incident = False

    @property
    def total(self) -> int:
        return self._total

    def for_budget(self, budget_id: str) -> int:
        return self._used.get(budget_id, 0)

    @property
    def blocked(self) -> bool:
        return self._incident or self._total > self._ceiling or bool(self._overdrawn)

    def replace(self, before: RequestRecord | None, after: RequestRecord) -> None:
        if after.reservation.scope.authorization != self._authorization:
            raise ValueError("Accounting record must retain the authorization")
        if before is not None and before.reservation != after.reservation:
            raise ValueError("Accounting update must preserve the reservation")
        budget_id = after.reservation.scope.budget_id
        if budget_id not in self._limits:
            raise ValueError("Accounting record is outside the authorization")
        previous = 0 if before is None else before.held.units + before.charged.units
        current = after.held.units + after.charged.units
        delta = current - previous
        self._total += delta
        self._used[budget_id] = self.for_budget(budget_id) + delta
        if self._used[budget_id] > self._limits[budget_id]:
            self._overdrawn.add(budget_id)
        else:
            self._overdrawn.discard(budget_id)
        self._incident |= after.exceeded_reservation
