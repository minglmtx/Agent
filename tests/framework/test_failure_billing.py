"""Original HTTP error -> shared spending stop -> evidence-only failed charge."""

import base64
import json
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.budget import Money
from lab_generate_skill.domain.budget_journal import BudgetReconciliationRequired
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.model_failure import FailureBillingPending
from lab_generate_skill.domain.model_request import ModelSendPlan
from failure_billing_fixtures import (
    fixture,
    fail_send,
    reconciler,
    other_request,
    FAILURE,
)
from test_file_request_ledger import operation


@pytest.mark.parametrize(
    "status,number,units",
    [(200, b"0.000000002", 2), (500, b"0", 0), (429, b"0.000000001", 1)],
)
def test_complete_error_bill_settles_once_and_reopens_next_work(
    tmp_path: Path, status: int, number: bytes, units: int
) -> None:
    f, _ = fixture(tmp_path)
    ref = fail_send(f, FAILURE.replace(b"0.000000002", number), status)
    next_request = other_request(f)
    with pytest.raises(BudgetReconciliationRequired) as error:
        f.ledger.reserve(
            f.plan.reservation.scope,
            next_request,
            Money(units=1),
            operation(next_request),
        )
    assert error.value.request_ids == (f.plan.reservation.request.request_id,)
    result = reconciler(f).reconcile(f.plan, ref, f.cleanup())
    assert result.settlement.record.state == "charged_failure"
    assert (
        result.settlement.record.charged.units == units
        and result.settlement.record.held.units == 0
    )
    assert f.store.read(result.fact.response_ref) == FAILURE.replace(
        b"0.000000002", number
    )
    assert reconciler(f).reconcile(f.plan, ref, f.cleanup()) == result
    reservation = f.ledger.reserve(
        f.plan.reservation.scope, next_request, Money(units=1), operation(next_request)
    )
    assert (
        f.ledger.mark_dispatching(reservation, 0, operation(next_request)).request
        == next_request
    )


@pytest.mark.parametrize(
    "body",
    [
        FAILURE.replace(b"0.000000002", b"null"),
        FAILURE.replace(b"0.000000002", b"-1"),
        FAILURE.replace(b"0.000000002", b"true"),
        FAILURE.replace(b"0.000000002", b"0.0000000001"),
        FAILURE.replace(b'"unit-error"', b'""'),
        b'{"error":{"message":"unknown"}}',
        b"not JSON",
        b'{"id":"unit","choices":null,"usage":{"cost":0}}',
    ],
)
def test_ambiguous_error_keeps_fence_and_original_reservation(
    tmp_path: Path, body: bytes
) -> None:
    f, _ = fixture(tmp_path)
    ref = fail_send(f, body)
    before = f.ledger.read(f.plan.reservation.request, f.cleanup())
    with pytest.raises(ValueError):
        reconciler(f).reconcile(f.plan, ref, f.cleanup())
    assert f.ledger.read(f.plan.reservation.request, f.cleanup()) == before
    assert before.held.units == 4 and before.state == "dispatching"
    another = other_request(f)
    with pytest.raises(BudgetReconciliationRequired):
        f.ledger.reserve(
            f.plan.reservation.scope, another, Money(units=1), operation(another)
        )


@pytest.mark.parametrize(
    "change",
    ["request", "operation", "reason", "status", "base64", "schema", "oversize"],
)
def test_actual_diagnostic_mismatch_never_settles(tmp_path: Path, change: str) -> None:
    f, _ = fixture(tmp_path)
    original = fail_send(f)
    value = json.loads(f.store.read(original))
    if change == "request":
        value["request"]["request_id"] = "different"
    if change == "operation":
        value["operation"]["operation_id"] = "different"
    if change == "reason":
        value["reason"] = "HTTP_IO"
    if change == "status":
        value["status"] = 307
    if change == "base64":
        value["body_base64"] = "broken%"
    if change == "schema":
        value["schema_version"] = "unknown/1"
    if change == "oversize":
        value["body_base64"] = base64.b64encode(b"x" * 1025).decode()
    ref = f.store.put(
        json.dumps(value).encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="model-transport-failure/1",
            visibility="private",
            producer="unit-mutated",
        ),
    )
    with pytest.raises((ValueError, OwnershipConflict)):
        reconciler(f).reconcile(f.plan, ref, f.cleanup())
    assert f.ledger.read(f.plan.reservation.request, f.cleanup()).state == "dispatching"


def test_denied_authority_retains_fact_and_shared_fence(tmp_path: Path) -> None:
    f, authority = fixture(tmp_path)
    ref = fail_send(f)
    authority.denied = True
    with pytest.raises(FailureBillingPending) as error:
        reconciler(f).reconcile(f.plan, ref, f.cleanup())
    assert error.value.fact_ref is not None and error.value.response_ref is not None
    assert isinstance(error.value.__cause__, OwnershipConflict)
    assert f.ledger.read(f.plan.reservation.request, f.cleanup()).held.units == 4
    authority.denied = False
    assert (
        reconciler(f).reconcile(f.plan, ref, f.cleanup()).settlement.record.state
        == "charged_failure"
    )


def test_invalid_cleanup_and_evidence_types_have_no_charge_effect(
    tmp_path: Path,
) -> None:
    f, _ = fixture(tmp_path)
    ref = fail_send(f)
    for op in (
        f.plan.operation,
        f.cleanup().model_copy(update={"parent_operation_id": "wrong"}),
    ):
        with pytest.raises(ValueError):
            reconciler(f).reconcile(f.plan, ref, op)
    with pytest.raises(ValidationError):
        reconciler(f).reconcile(cast(ModelSendPlan, None), ref, f.cleanup())
    with pytest.raises(ValidationError):
        reconciler(f).reconcile(f.plan, cast(EvidenceRef, None), f.cleanup())
    assert f.ledger.read(f.plan.reservation.request, f.cleanup()).held.units == 4


def test_corrupt_original_cas_prevents_billing(tmp_path: Path) -> None:
    f, _ = fixture(tmp_path)
    ref = fail_send(f)
    (f.root / "evidence" / "blobs" / ref.sha256).write_bytes(b"corrupt")
    with pytest.raises(EvidenceIntegrityError):
        reconciler(f).reconcile(f.plan, ref, f.cleanup())
    assert f.ledger.read(f.plan.reservation.request, f.cleanup()).state == "dispatching"
