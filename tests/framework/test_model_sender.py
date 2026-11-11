"""Sender composition against actual immutable bytes and shared budget ledger."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.budget import Money
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    EvidenceNotFound,
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.model_request import (
    ModelSendPlan,
    ModelSendLimits,
    ResolvedModelRequest,
)
from lab_generate_skill.domain.model_response import ModelSendUnconfirmed
from model_sender_fixtures import SendFixture, send_fixture, sender


@pytest.fixture
def fixture(tmp_path: Path) -> SendFixture:
    return send_fixture(tmp_path)


def test_actual_send_settlement_reopen_and_exact_reconcile(
    fixture: SendFixture,
) -> None:
    f = fixture
    result = f.sender().generate(f.plan)
    assert len(f.transport.calls) == 1
    resolved = f.transport.calls[0]
    assert resolved.input_bytes == f.store.read(f.plan.input_ref)
    assert resolved.parameters_bytes == f.store.read(f.plan.parameters_ref)
    assert f.store.read(result.fact.response_ref) == f.transport.reply_bytes
    assert result.settlement.record.state == "succeeded"
    assert result.settlement.record.charged.units == 2
    assert result.settlement.record.held.units == 0
    reopened = sender(f.root, f.plan, f.transport)
    assert reopened.reconcile(f.plan, result.fact_ref, f.cleanup()) == result
    with pytest.raises(ModelSendUnconfirmed) as error:
        reopened.generate(f.plan)
    assert isinstance(error.value.__cause__, DispatchAlreadyCommitted)
    assert len(f.transport.calls) == 1


@pytest.mark.parametrize("response", [b"", b"\xff\x00", b"x" * 1024])
def test_empty_binary_and_limit_response_preserved(
    fixture: SendFixture, response: bytes
) -> None:
    fixture.transport.reply_bytes = response
    result = fixture.sender().generate(fixture.plan)
    assert fixture.store.read(result.fact.response_ref) == response


@pytest.mark.parametrize("charge", [None, Money(units=0), Money(units=6)])
def test_unknown_zero_and_overage_keep_exact_accounting(
    fixture: SendFixture, charge: Money | None
) -> None:
    f = fixture
    f.transport.charge = charge
    result = f.sender().generate(f.plan)
    record = result.settlement.record
    assert result.fact.charge == charge
    assert record.state == ("uncertain" if charge is None else "succeeded")
    assert record.held.units == (4 if charge is None else 0)
    assert record.exceeded_reservation == (charge is not None and charge.units > 4)


@pytest.mark.parametrize(
    "changes",
    [
        {"input_ref": None},
        {"limits": None},
        {"operation": None},
        {"extra": 1},
        {"schema_version": "model-send-plan/0"},
    ],
)
def test_invalid_plan_has_no_ledger_or_transport_effect(
    fixture: SendFixture, changes: dict[str, object]
) -> None:
    f = fixture
    with pytest.raises(ValidationError):
        f.sender().generate(f.plan.model_copy(update=changes))
    assert not f.transport.calls and f.authority.calls == 0
    with pytest.raises(EvidenceNotFound):
        f.ledger.read(f.plan.reservation.request, f.cleanup())


@pytest.mark.parametrize(
    "value", [None, True, 0, -1, 1.5, "100", [], 64 * 1024 * 1024 + 1]
)
def test_byte_limits_are_strict_bounded_integers(value: object) -> None:
    with pytest.raises(ValidationError):
        ModelSendLimits.model_validate(
            dict(max_input_bytes=value, max_parameters_bytes=1, max_response_bytes=1)
        )


@pytest.mark.parametrize("field", ["input_ref", "parameters_ref"])
def test_reference_digest_scope_and_visibility_rejected(
    fixture: SendFixture, field: str
) -> None:
    f = fixture
    ref = getattr(f.plan, field)
    for changes in (
        {"sha256": "f" * 64},
        {"visibility": "public"},
        {"size_bytes": 0},
        {"content_schema": "unrelated/1"},
    ):
        with pytest.raises(ValidationError):
            f.sender().generate(
                f.plan.model_copy(update={field: ref.model_copy(update=changes)})
            )
    assert not f.transport.calls


@pytest.mark.parametrize(
    "field", ["reserve_operation", "operation", "settlement_operation"]
)
def test_wrong_operation_scope_or_reused_identity(
    fixture: SendFixture, field: str
) -> None:
    f = fixture
    op = getattr(f.plan, field)
    with pytest.raises(ValidationError):
        f.sender().generate(
            f.plan.model_copy(
                update={field: op.model_copy(update={"attempt_id": "other"})}
            )
        )
    with pytest.raises(ValidationError):
        f.sender().generate(
            f.plan.model_copy(update={"reserve_operation": f.plan.operation})
        )
    assert not f.transport.calls


def test_denied_or_expired_preflight_has_no_reservation(fixture: SendFixture) -> None:
    f = fixture
    f.authority.denied = True
    with pytest.raises(OwnershipConflict):
        f.sender().generate(f.plan)
    f.authority.denied = False
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    plan = f.plan.model_copy(
        update={
            "settlement_operation": f.plan.settlement_operation.model_copy(
                update={"deadline": past}
            )
        }
    )
    with pytest.raises(OperationStopped):
        f.sender().generate(plan)
    assert not f.transport.calls
    with pytest.raises(EvidenceNotFound):
        f.ledger.read(f.plan.reservation.request, f.cleanup())


def test_reconcile_rejects_wrong_cleanup_and_actual_fact(fixture: SendFixture) -> None:
    f = fixture
    result = f.sender().generate(f.plan)
    with pytest.raises(ValueError):
        f.sender().reconcile(f.plan, result.fact_ref, f.plan.operation)
    with pytest.raises(ValueError):
        f.sender().reconcile(
            f.plan,
            result.fact_ref,
            f.cleanup().model_copy(update={"parent_operation_id": "wrong"}),
        )
    with pytest.raises(ValueError):
        f.sender().reconcile(f.plan, f.plan.input_ref, f.cleanup())
    assert len(f.transport.calls) == 1


def test_resolved_bytes_reject_forged_digest_or_wrong_type(
    fixture: SendFixture,
) -> None:
    f = fixture
    values = dict(
        request=f.plan.reservation.request,
        input_bytes=f.store.read(f.plan.input_ref),
        parameters_bytes=f.store.read(f.plan.parameters_ref),
        limits=f.plan.limits,
    )
    for invalid in (b"changed", "text", None, b""):
        with pytest.raises(ValidationError):
            ResolvedModelRequest.model_validate({**values, "input_bytes": invalid})
    with pytest.raises(ValidationError):
        f.sender().generate(cast(ModelSendPlan, None))


@pytest.mark.parametrize("corrupt", [False, True])
def test_missing_or_corrupt_actual_input_stops_before_reserve(
    fixture: SendFixture, corrupt: bool
) -> None:
    f = fixture
    path = f.root / "evidence" / "blobs" / f.plan.input_ref.sha256
    if corrupt:
        path.write_bytes(b"changed")
    else:
        path.unlink()
    with pytest.raises(EvidenceIntegrityError if corrupt else EvidenceNotFound):
        f.sender().generate(f.plan)
    assert not f.transport.calls and f.authority.calls == 0


def test_other_request_fact_cannot_settle_this_request(fixture: SendFixture) -> None:
    from lab_generate_skill.adapters.models.send_evidence import ModelSendEvidence

    f = fixture
    result = f.sender().generate(f.plan)
    fact = result.fact.model_copy(
        update={
            "request": result.fact.request.model_copy(update={"request_id": "other"})
        }
    )
    ref = ModelSendEvidence(f.store).publish(
        fact, DeadlineControl(5, "fixture-publish")
    )
    with pytest.raises(OwnershipConflict):
        f.sender().reconcile(f.plan, ref, f.cleanup())
    assert len(f.transport.calls) == 1
