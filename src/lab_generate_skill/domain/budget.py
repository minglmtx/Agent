"""Exact USD amounts and immutable shared authorization scopes; no I/O.

Amounts are integer nanodollars (10^-9 USD), never float totals. Provider
conversion must be exact or explicitly preserve an unsupported charge as
unresolved; this module does not guess exchange rates or round reported costs.
Constructing authorization metadata is not proof of actual user permission.
"""

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .evidence import EvidenceRef
from .validation import Contract, Identifier


class Money(Contract):
    schema_version: Literal["money/1"] = "money/1"
    currency: Literal["USD"] = "USD"
    scale: Literal[9] = 9
    units: int = Field(ge=0)

    @field_validator("scale", mode="before")
    @classmethod
    def integer_scale(cls, value: object) -> object:
        # Literal equality alone can accept 9.0; this wire field is an integer.
        if type(value) is not int:
            raise ValueError("Money scale must be an integer")
        return value


class BudgetLimit(Contract):
    schema_version: Literal["budget-limit/1"] = "budget-limit/1"
    budget_id: Identifier
    ceiling: Money


class BudgetAuthorization(Contract):
    """Total and subbudget limits are checked together, not independently."""

    schema_version: Literal["budget-authorization/1"] = "budget-authorization/1"
    authorization_id: Identifier
    authorization_ref: EvidenceRef
    ceiling: Money
    budgets: tuple[BudgetLimit, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_subbudgets(self) -> Self:
        if len({item.budget_id for item in self.budgets}) != len(self.budgets):
            raise ValueError("Budget IDs must be unique in an authorization")
        if any(item.ceiling.units > self.ceiling.units for item in self.budgets):
            raise ValueError("A subbudget cannot exceed the authorization ceiling")
        return self


class BudgetScope(Contract):
    schema_version: Literal["budget-scope/1"] = "budget-scope/1"
    authorization: BudgetAuthorization
    budget_id: Identifier

    @model_validator(mode="after")
    def known_budget(self) -> Self:
        if not any(
            item.budget_id == self.budget_id for item in self.authorization.budgets
        ):
            raise ValueError("Budget is not part of this authorization")
        return self

    @property
    def ceiling(self) -> Money:
        return next(
            item.ceiling
            for item in self.authorization.budgets
            if item.budget_id == self.budget_id
        )
