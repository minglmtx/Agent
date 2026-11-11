"""Billing storage/commit failures preserve original fence, evidence and causes."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.models.failure_billing import LedgerFailureBilling
from lab_generate_skill.domain.budget import Money
from lab_generate_skill.domain.budget_journal import BudgetReconciliationRequired
from lab_generate_skill.domain.model_failure import FailureBillingPending
from lab_generate_skill.runtime.lifecycle import OperationGuards
from failure_billing_fixtures import fixture, fail_send, reconciler, other_request
from test_file_request_ledger import NoCancel, operation
from test_model_sender_faults import FaultStore, FaultLedger


@pytest.mark.parametrize(
    "schema", ["actor-model-response/1", "model-failure-billing/1"]
)
@pytest.mark.parametrize("after", [False, True])
def test_evidence_write_and_cleanup_failures_do_not_reopen_spending(
    tmp_path: Path, schema: str, after: bool
) -> None:
    f, _ = fixture(tmp_path)
    original = fail_send(f)
    store = FaultStore(f.store, schema, after)
    billing = LedgerFailureBilling(
        f.ledger, store, OperationGuards(SystemClock(), NoCancel())
    )
    with pytest.raises(FailureBillingPending) as error:
        billing.reconcile(f.plan, original, f.cleanup())
    assert error.value.transport_ref == original and isinstance(
        error.value.__cause__, ExceptionGroup
    )
    assert len(error.value.__cause__.exceptions) == 2
    assert (error.value.response_ref is not None) == (
        schema == "model-failure-billing/1"
    )
    assert (store.written is not None) == after
    if store.written is not None:
        assert f.store.read(store.written)
    another = other_request(f)
    with pytest.raises(BudgetReconciliationRequired):
        f.ledger.reserve(
            f.plan.reservation.scope, another, Money(units=1), operation(another)
        )
    assert (
        reconciler(f)
        .reconcile(f.plan, original, f.cleanup())
        .settlement.record.charged.units
        == 2
    )


@pytest.mark.parametrize("fault", ["settle_before", "settle_ack"])
def test_failed_settlement_or_lost_ack_reconciles_only_original_charge(
    tmp_path: Path, fault: str
) -> None:
    f, _ = fixture(tmp_path)
    original = fail_send(f)
    billing = LedgerFailureBilling(
        FaultLedger(f.ledger, fault),
        f.store,
        OperationGuards(SystemClock(), NoCancel()),
    )
    with pytest.raises(FailureBillingPending) as error:
        billing.reconcile(f.plan, original, f.cleanup())
    assert error.value.fact_ref is not None and error.value.response_ref is not None
    record = f.ledger.read(f.plan.reservation.request, f.cleanup())
    assert record.state == (
        "dispatching" if fault == "settle_before" else "charged_failure"
    )
    result = reconciler(f).reconcile(f.plan, original, f.cleanup())
    assert result.settlement.record.charged.units == 2
    assert reconciler(f).reconcile(f.plan, original, f.cleanup()) == result
