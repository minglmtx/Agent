"""Dispatch/response/settlement failures preserve original facts without resend."""

from lab_generate_skill.ports.lifecycle import OperationControl

from pathlib import Path
from datetime import datetime, timedelta, timezone
import pytest
from lab_generate_skill.domain.budget import BudgetScope, Money
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.generation import (
    DispatchPermit,
    OutcomeProof,
    RequestIdentity,
    RequestReceipt,
    RequestRecord,
    Reservation,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_response import ModelSendUnconfirmed
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.requests import RequestLedger
from model_sender_fixtures import SendFixture, send_fixture
from lab_generate_skill.adapters.models.paid_sender import LedgerModelSender
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_file_request_ledger import NoCancel


class FaultLedger:
    def __init__(self, inner: RequestLedger, fault: str) -> None:
        self.inner, self.fault = inner, fault

    def reserve(
        self,
        scope: BudgetScope,
        request: RequestIdentity,
        ceiling: Money,
        op: OperationContext,
    ) -> Reservation:
        return self.inner.reserve(scope, request, ceiling, op)

    def mark_dispatching(
        self, reservation: Reservation, expected_revision: int, op: OperationContext
    ) -> DispatchPermit:
        permit = self.inner.mark_dispatching(reservation, expected_revision, op)
        if self.fault == "dispatch_ack":
            raise ExceptionGroup(
                "commit and cleanup", [OSError("lost ack"), OSError("close")]
            )
        if self.fault == "bad_permit":
            return permit.model_copy(update={"dispatch_operation_id": "forged"})
        return permit

    def read(self, request: RequestIdentity, op: OperationContext) -> RequestRecord:
        return self.inner.read(request, op)

    def settle(
        self,
        request: RequestIdentity,
        proof: OutcomeProof,
        expected_revision: int,
        op: OperationContext,
    ) -> RequestReceipt:
        if self.fault == "settle_before":
            raise OSError("settlement unavailable")
        receipt = self.inner.settle(request, proof, expected_revision, op)
        if self.fault == "settle_ack":
            raise OSError("settled but lost ack")
        return receipt


class FaultStore:
    def __init__(self, inner: EvidenceStore, schema: str, after: bool) -> None:
        self.inner, self.schema, self.after = inner, schema, after
        self.written: EvidenceRef | None = None

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        return self.inner.read(reference, control=control)

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        if metadata.content_schema != self.schema:
            return self.inner.put(data, metadata, control=control)
        if self.after:
            self.written = self.inner.put(data, metadata, control=control)
        raise ExceptionGroup(
            "storage and cleanup", [OSError("write/ack"), OSError("close")]
        )


@pytest.fixture
def fixture(tmp_path: Path) -> SendFixture:
    return send_fixture(tmp_path)


@pytest.mark.parametrize("fault", ["dispatch_ack", "bad_permit"])
def test_lost_dispatch_or_wrong_permit_never_reaches_transport(
    fixture: SendFixture, fault: str
) -> None:
    f = fixture
    with pytest.raises(ModelSendUnconfirmed) as error:
        f.sender(ledger=FaultLedger(f.ledger, fault)).generate(f.plan)
    assert error.value.stage == "dispatch" and not f.transport.calls
    assert isinstance(
        error.value.__cause__,
        ExceptionGroup if fault == "dispatch_ack" else OwnershipConflict,
    )
    assert f.ledger.read(f.plan.reservation.request, f.cleanup()).state == "dispatching"
    with pytest.raises(ModelSendUnconfirmed) as repeated:
        f.sender().generate(f.plan)
    assert isinstance(repeated.value.__cause__, DispatchAlreadyCommitted)
    assert not f.transport.calls


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("unknown provider result"),
        OSError("disconnect"),
        KeyboardInterrupt(),
    ],
)
def test_transport_failure_retains_reservation_and_full_cause(
    fixture: SendFixture, failure: BaseException
) -> None:
    f = fixture
    f.transport.error = failure
    with pytest.raises(ModelSendUnconfirmed) as error:
        f.sender().generate(f.plan)
    assert error.value.__cause__ is failure
    assert error.value.stage == "send" and error.value.fact_ref is None
    record = f.ledger.read(f.plan.reservation.request, f.cleanup())
    assert record.state == "dispatching" and record.held.units == 4
    with pytest.raises(ModelSendUnconfirmed):
        f.sender().generate(f.plan)
    assert len(f.transport.calls) == 1


@pytest.mark.parametrize("schema", ["actor-model-response/1", "model-send-fact/1"])
@pytest.mark.parametrize("after", [False, True])
def test_storage_failures_keep_known_references_and_actual_disk_state(
    fixture: SendFixture, schema: str, after: bool
) -> None:
    f = fixture
    store = FaultStore(f.store, schema, after)
    with pytest.raises(ModelSendUnconfirmed) as error:
        f.sender(store=store).generate(f.plan)
    pending = error.value
    assert isinstance(pending.__cause__, ExceptionGroup)
    assert len(pending.__cause__.exceptions) == 2
    assert pending.fact_ref is None
    if schema == "model-send-fact/1":
        assert pending.response_ref is not None
        assert f.store.read(pending.response_ref) == f.transport.reply_bytes
    else:
        assert pending.response_ref is None
    assert (store.written is not None) == after
    if store.written is not None:
        assert f.store.read(store.written)
        if schema == "model-send-fact/1":
            result = f.sender().reconcile(f.plan, store.written, f.cleanup())
            assert result.settlement.record.state == "succeeded"
    with pytest.raises(ModelSendUnconfirmed):
        f.sender().generate(f.plan)
    assert len(f.transport.calls) == 1


@pytest.mark.parametrize("fault", ["settle_before", "settle_ack"])
def test_settlement_failure_and_fresh_sender_reconcile_no_second_send(
    fixture: SendFixture, fault: str
) -> None:
    f = fixture
    with pytest.raises(ModelSendUnconfirmed) as error:
        f.sender(ledger=FaultLedger(f.ledger, fault)).generate(f.plan)
    pending = error.value
    assert pending.stage == "settlement" and pending.fact_ref is not None
    assert (
        pending.response_ref is not None
        and f.store.read(pending.response_ref) == f.transport.reply_bytes
    )
    before = f.ledger.read(f.plan.reservation.request, f.cleanup())
    assert before.state == ("dispatching" if fault == "settle_before" else "succeeded")
    result = f.sender().reconcile(f.plan, pending.fact_ref, f.cleanup())
    assert result.settlement.record.charged.units == 2
    assert f.sender().reconcile(f.plan, pending.fact_ref, f.cleanup()) == result
    assert len(f.transport.calls) == 1


@pytest.mark.parametrize("fault", ["identity", "oversize"])
def test_wrong_or_oversized_response_is_saved_but_not_settled(
    fixture: SendFixture, fault: str
) -> None:
    f = fixture
    if fault == "identity":
        f.transport.reply_request = "another"
    else:
        f.transport.reply_bytes = b"x" * 1025
    with pytest.raises(ModelSendUnconfirmed) as error:
        f.sender().generate(f.plan)
    pending = error.value
    assert pending.response_ref is not None and pending.fact_ref is None
    assert f.store.read(pending.response_ref) == f.transport.reply_bytes
    assert f.ledger.read(f.plan.reservation.request, f.cleanup()).held.units == 4
    assert len(f.transport.calls) == 1


class AdvancingClock:
    def __init__(self) -> None:
        self.start = datetime.now(timezone.utc)
        self.elapsed = 0.0

    def utcnow(self) -> datetime:
        return self.start + timedelta(seconds=self.elapsed)

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.elapsed += seconds


@pytest.mark.parametrize("cleanup_live", [False, True])
def test_deadline_after_return_preserves_fact_and_uses_independent_cleanup(
    fixture: SendFixture, monkeypatch: pytest.MonkeyPatch, cleanup_live: bool
) -> None:
    from lab_generate_skill.domain.model_request import (
        ModelSendPlan,
        ResolvedModelRequest,
    )
    from lab_generate_skill.domain.model_response import ProviderReply

    f = fixture
    clock = AdvancingClock()
    plan = ModelSendPlan.model_validate(
        f.plan.model_copy(
            update={
                "settlement_operation": f.plan.settlement_operation.model_copy(
                    update={
                        "deadline": clock.start
                        + timedelta(seconds=60 if cleanup_live else 30)
                    }
                )
            }
        )
    )
    original = f.transport.send

    def delayed(request: ResolvedModelRequest, op: OperationContext) -> ProviderReply:
        reply = original(request, op)
        clock.sleep(31)
        return reply

    monkeypatch.setattr(f.transport, "send", delayed)
    instance = LedgerModelSender(
        f.ledger, f.transport, f.store, OperationGuards(clock, NoCancel()), f.authority
    )
    if cleanup_live:
        result = instance.generate(plan)
        assert result.settlement.record.state == "succeeded"
    else:
        with pytest.raises(ModelSendUnconfirmed) as error:
            instance.generate(plan)
        assert error.value.fact_ref is not None
        result = f.sender().reconcile(plan, error.value.fact_ref, f.cleanup())
        assert result.settlement.record.state == "succeeded"
    assert len(f.transport.calls) == 1
