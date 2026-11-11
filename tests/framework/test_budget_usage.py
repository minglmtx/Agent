"""Accounting differences versus independent full sums at every history prefix."""

import pytest
from lab_generate_skill.domain.budget import BudgetScope, Money
from lab_generate_skill.domain.budget_usage import BudgetUsage
from lab_generate_skill.domain.generation import OutcomeProof, RequestRecord
from lab_generate_skill.domain.request_ledger import (
    BudgetSnapshot,
    ReserveEntry,
    reserve_request,
    dispatch_request,
    settle_request,
)
from budget_capacity_reference import reference_projection
from budget_capacity_fixtures import snapshot
from test_request_budget import scope, reserve, request, proof, ref


@pytest.mark.parametrize("charge", [0, 2, 6, 8, 11])
def test_cross_subbudget_usage_and_sticky_incidents_match_full_sums(
    scope: BudgetScope, charge: int
) -> None:
    history = reserve(scope)
    history, _ = reserve_request(
        history,
        BudgetScope(authorization=scope.authorization, budget_id="b"),
        request("second", budget="b"),
        Money(units=3),
        "reserve-second",
    )
    first = history.project()[0]
    history = dispatch_request(history, first.reservation, 0, "dispatch-first")
    failed = proof(request(), "charged_failure", units=charge)
    history, receipt = settle_request(history, request(), failed, 1, "fail")
    correction = OutcomeProof(
        request=request(),
        outcome="charge_corrected",
        evidence=(ref("e"),),
        charge=Money(units=1),
        supersedes=failed.digest,
    )
    history, _ = settle_request(
        history, request(), correction, receipt.record.revision, "correct"
    )
    usage = BudgetUsage(scope.authorization)
    records: dict[str, RequestRecord] = {}
    for index, after in enumerate(history.replay_changes(), start=1):
        key = after.reservation.request.request_id
        usage.replace(records.get(key), after)
        records[key] = after
        expected = reference_projection(
            history.model_copy(update={"entries": history.entries[:index]})
        )
        assert tuple(records.values()) == expected
        total = sum(record.held.units + record.charged.units for record in expected)
        assert usage.total == total
        for limit in scope.authorization.budgets:
            assert usage.for_budget(limit.budget_id) == sum(
                r.held.units + r.charged.units
                for r in expected
                if r.reservation.scope.budget_id == limit.budget_id
            )
        blocked = (
            any(r.exceeded_reservation for r in expected)
            or total > scope.authorization.ceiling.units
            or any(
                usage.for_budget(limit.budget_id) > limit.ceiling.units
                for limit in scope.authorization.budgets
            )
        )
        assert usage.blocked == blocked
    assert usage.total == 4 and usage.blocked == (charge > 4)
    fresh = BudgetUsage(scope.authorization)
    assert fresh.total == 0 and not fresh.blocked and fresh.for_budget("missing") == 0


@pytest.mark.parametrize(
    "fault", ["duplicate", "alias", "operation", "overspend", "authorization"]
)
def test_optimized_financial_replay_rejects_same_bad_prefix_as_reference(
    fault: str,
) -> None:
    value = snapshot(2).history
    first, second = value.entries
    assert isinstance(first, ReserveEntry) and isinstance(second, ReserveEntry)
    if fault == "duplicate":
        second = first
    elif fault == "operation":
        second = second.model_copy(update={"operation_id": first.operation_id})
    elif fault == "alias":
        identity = first.reservation.request.model_copy(
            update={"request_id": "different"}
        )
        second = second.model_copy(
            update={
                "reservation": second.reservation.model_copy(
                    update={"request": identity}
                )
            }
        )
    elif fault == "overspend":
        first = first.model_copy(
            update={
                "reservation": first.reservation.model_copy(
                    update={"ceiling": Money(units=1000000)}
                )
            }
        )
    else:
        changed = value.authorization.model_copy(update={"authorization_ref": ref("f")})
        second = second.model_copy(
            update={
                "reservation": second.reservation.model_copy(
                    update={"scope": BudgetScope(authorization=changed, budget_id="a")}
                )
            }
        )
    bad = value.model_copy(update={"entries": (first, second)})
    with pytest.raises(ValueError) as expected:
        reference_projection(bad)
    with pytest.raises(ValueError, match=str(expected.value)):
        bad.project()


def test_accounting_mismatch_rejected_before_mutation(scope: BudgetScope) -> None:
    history = reserve(scope)
    record = history.project()[0]
    usage = BudgetUsage(scope.authorization)
    usage.replace(None, record)
    other = reserve(scope, request("other")).project()[0]
    with pytest.raises(ValueError, match="reservation"):
        usage.replace(record, other)
    foreign = record.model_copy(
        update={
            "reservation": record.reservation.model_copy(
                update={
                    "scope": BudgetScope(
                        authorization=scope.authorization.model_copy(
                            update={"authorization_ref": ref("f")}
                        ),
                        budget_id="a",
                    )
                }
            )
        }
    )
    with pytest.raises(ValueError, match="authorization"):
        usage.replace(record, foreign)
    assert usage.total == 4 and usage.for_budget("a") == 4 and not usage.blocked
