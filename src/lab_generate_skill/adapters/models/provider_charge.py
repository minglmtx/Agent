"""Exact provider JSON amount conversion; unsupported prices remain unknown."""

from decimal import Decimal
from lab_generate_skill.domain.budget import Money


def exact_charge(cost: object) -> Money | None:
    charge = None
    if isinstance(cost, (int, Decimal)) and not isinstance(cost, bool):
        amount = Decimal(cost)
        # Bound exponent/digits before arithmetic: no giant decimal allocation.
        if amount.is_finite() and 0 <= amount <= Decimal("1000000000"):
            parts = amount.as_tuple()
            digits, exponent = list(parts.digits), parts.exponent
            if isinstance(exponent, int):
                while digits and digits[-1] == 0:
                    digits.pop()
                    exponent += 1
                if not digits:
                    charge = Money(units=0)
                elif exponent >= -9:
                    coefficient = int("".join(map(str, digits)))
                    charge = Money(units=coefficient * 10 ** (exponent + 9))
    return charge
