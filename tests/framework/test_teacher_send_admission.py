"""Actual file state at final Teacher gate; all physical/model/fee rights unit-only."""

from dataclasses import replace
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.teacher_send_admission import (
    ConstructionTeacherSendAuthority,
)
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    InvalidTransition,
    DispatchAlreadyCommitted,
    EvidenceNotFound,
    RevisionConflict,
    OperationStopped,
)
from lab_generate_skill.domain.model_request import ModelSendPlan, ResolvedModelRequest
from lab_generate_skill.domain.model_response import ModelSendFact
from lab_generate_skill.domain.budget import Money
from lab_generate_skill.domain.construction import CallUncertain
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.ports.requests import RequestLedger
from lab_generate_skill.ports.model import ModelSendAuthority
from lab_generate_skill.ports.lifecycle import OperationControl
from teacher_send_admission_fixtures import send_case
from test_teacher_source_admission_boundaries import error_stop
from construction_storage_fixtures import put
from test_teacher_assembly import paid_files
from test_run_journal import command


@pytest.mark.parametrize("reserved", [False, True])
def test_live_gate_allows_original_ready_or_known_undispatched_reservation_and_sends_once(
    tmp_path: Path, reserved: bool
) -> None:
    c = send_case(tmp_path / "case")
    n = c.native
    plan = c.published.bound.plan
    if reserved:
        n.ledger.reserve(
            plan.send.reservation.scope,
            plan.send.reservation.request,
            plan.send.reservation.ceiling,
            plan.send.reserve_operation,
        )
    before = paid_files(n)
    c.gate.verify(plan.send, c.resolved)
    c.gate.verify(plan.send, c.resolved)
    assert paid_files(n) == before and not n.transport.calls
    result = c.teacher().revise(plan.revision, plan.send.operation)
    assert result.request_id == plan.revision.request_id and len(n.transport.calls) == 1
    record = n.ledger.read(
        plan.send.reservation.request, plan.send.settlement_operation
    )
    assert record.state == "succeeded" and record.charged.units == 2
    known = paid_files(n)
    with pytest.raises(DispatchAlreadyCommitted):
        c.teacher().revise(plan.revision, plan.send.operation)
    assert len(n.transport.calls) == 1 and paid_files(n) == known


@pytest.mark.parametrize(
    "fault",
    [
        "stopped",
        "claim_denied",
        "provider_denied",
        "construction_unknown",
        "limits",
        "extreme_changed_slot",
        "reserved_wrong_operation",
    ],
)
def test_gate_denies_changed_or_unqualified_live_call_before_reserve_or_transport(
    tmp_path: Path, fault: str
) -> None:
    c = send_case(tmp_path / "case")
    n = c.native
    plan = c.published.bound.plan.send
    resolved = c.resolved
    if fault == "stopped":
        current = c.source.runs.read(plan.operation)
        stopping = error_stop(current, c.source)
        c.source.runs.append(stopping, current.revision, stopping.event.operation)
    elif fault == "claim_denied":
        n.source.data.claim_authority.denied = True
    elif fault == "provider_denied":
        n.send_authority.denied = True
    elif fault == "construction_unknown":
        old = n.deps.journal.read(plan.operation)
        evidence = put(
            n.source.data.store,
            {"unknown_request": plan.reservation.request.request_id},
        )
        event = CallUncertain(
            operation=command("live-teacher-original-unknown"),
            request_id=plan.reservation.request.request_id,
            evidence_ref=evidence,
        )
        n.deps.journal.append(event, old.revision, event.operation)
    elif fault == "limits":
        resolved = resolved.model_copy(
            update={
                "limits": resolved.limits.model_copy(
                    update={"max_response_bytes": 12345}
                )
            }
        )
    elif fault == "extreme_changed_slot":
        identity = plan.reservation.request.model_copy(
            update={"candidate_index": 2147483647}
        )
        plan = plan.model_copy(
            update={
                "reservation": plan.reservation.model_copy(update={"request": identity})
            }
        )
        resolved = resolved.model_copy(update={"request": identity})
    else:
        n.ledger.reserve(
            plan.reservation.scope,
            plan.reservation.request,
            plan.reservation.ceiling,
            plan.reserve_operation.model_copy(
                update={"operation_id": "different-reservation-operation"}
            ),
        )
    before = paid_files(n)
    with pytest.raises(
        (OwnershipConflict, InvalidTransition, DispatchAlreadyCommitted)
    ):
        c.gate.verify(plan, resolved)
    assert paid_files(n) == before and not n.transport.calls
    if fault != "reserved_wrong_operation":
        with pytest.raises(EvidenceNotFound):
            n.ledger.read(plan.reservation.request, plan.settlement_operation)


@pytest.mark.parametrize("state", ["dispatching", "uncertain", "succeeded"])
def test_original_dispatch_or_outcome_is_never_replayed_even_while_call_pending(
    tmp_path: Path, state: str
) -> None:
    c = send_case(tmp_path / "case")
    n = c.native
    plan = c.published.bound.plan.send
    n.ledger.reserve(
        plan.reservation.scope,
        plan.reservation.request,
        plan.reservation.ceiling,
        plan.reserve_operation,
    )
    n.ledger.mark_dispatching(plan.reservation, 0, plan.operation)
    if state != "dispatching":
        raw_ref = n.source.data.store.put(
            n.transport.reply_bytes,
            EvidenceMetadata(
                media_type="application/json",
                content_schema="teacher-model-response/1",
                visibility="private",
                producer="unit-original-live-send-fact",
            ),
        )
        fact = ModelSendFact(
            request=plan.reservation.request,
            operation=plan.operation,
            response_ref=raw_ref,
            provider_request_id="unit-provider-1",
            charge=None if state == "uncertain" else Money(units=2),
        )
        ref = put(n.source.data.store, fact, "model-send-fact/1")
        n.ledger.settle(
            plan.reservation.request, fact.proof(ref), 1, plan.settlement_operation
        )
    before = paid_files(n)
    with pytest.raises(DispatchAlreadyCommitted):
        c.gate.verify(plan, c.resolved)
    assert paid_files(n) == before and not n.transport.calls
    assert (
        n.deps.journal.read(plan.operation).project().pending_call
        == c.published.bound.plan.call
    )


@pytest.mark.parametrize("bad", [None, True, 0, "", {}, []])
@pytest.mark.parametrize("target", ["plan", "request"])
def test_bad_send_input_is_rejected_before_original_authority_or_paid_state(
    tmp_path: Path, bad: object, target: str
) -> None:
    c = send_case(tmp_path / "case")
    calls = c.native.send_authority.calls
    before = paid_files(c.native)
    with pytest.raises(ValidationError):
        c.gate.verify(
            (
                cast(ModelSendPlan, bad)
                if target == "plan"
                else c.published.bound.plan.send
            ),
            cast(ResolvedModelRequest, bad) if target == "request" else c.resolved,
        )
    assert c.native.send_authority.calls == calls and paid_files(c.native) == before


@pytest.mark.parametrize(
    "fault", ["run_changes", "claim_revoked", "ledger_read_timeout", "cancel"]
)
def test_in_check_race_cancellation_or_read_failure_never_dispatches(
    tmp_path: Path, fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = send_case(tmp_path / "case")
    n = c.native
    plan = c.published.bound.plan.send
    primary: BaseException | None = None
    if fault in ("run_changes", "claim_revoked"):
        original = n.send_authority.verify
        calls = 0

        def change_on_second(
            plan: ModelSendPlan, request: ResolvedModelRequest
        ) -> None:
            nonlocal calls
            original(plan, request)
            calls += 1
            if calls == 2:
                if fault == "claim_revoked":
                    n.source.data.claim_authority.denied = True
                else:
                    old = c.source.runs.read(plan.operation)
                    event = error_stop(old, c.source)
                    c.source.runs.append(event, old.revision, event.event.operation)

        monkeypatch.setattr(n.send_authority, "verify", change_on_second)
        expected: type[BaseException] = (
            RevisionConflict if fault == "run_changes" else OwnershipConflict
        )
    elif fault == "ledger_read_timeout":
        primary = TimeoutError("Original paid ledger read timed out")

        def fail(reference: object, operation: OperationContext) -> None:
            assert primary is not None
            raise primary

        monkeypatch.setattr(n.ledger, "read", fail)
        expected = TimeoutError
    else:
        # The frozen original operation has no cancellation ref; bind a stopped
        # control explicitly, never modify its immutable operation or attempt.
        def cancelled(operation: OperationContext) -> OperationControl:
            class Stopped:
                def checkpoint(self) -> float:
                    raise OperationStopped("CANCELLED", operation.operation_id)

                def wait(self, seconds: float) -> None:
                    raise AssertionError("No wait")

            return cast(OperationControl, Stopped())

        monkeypatch.setattr(n.source.controls, "bind", cancelled)
        expected = OperationStopped
    before = paid_files(n)
    with pytest.raises(expected) as saved:
        c.gate.verify(plan, c.resolved)
    if primary is not None:
        assert saved.value is primary
    assert paid_files(n) == before and not n.transport.calls


@pytest.mark.parametrize("dependency", ["runs", "provider", "requests", "claims"])
def test_final_gate_has_no_missing_live_run_or_provider_default(
    tmp_path: Path, dependency: str
) -> None:
    c = send_case(tmp_path / "case")
    if dependency == "runs":
        deps = replace(c.gate.deps, runs=cast(RunJournal, None))
    elif dependency == "provider":
        deps = replace(c.gate.deps, original=cast(ModelSendAuthority, None))
    elif dependency == "requests":
        deps = replace(c.gate.deps, requests=cast(RequestLedger, None))
    else:
        deps = replace(c.gate.deps, claims=cast(SourceClaims, None))
    with pytest.raises(ValueError, match="Original Teacher"):
        ConstructionTeacherSendAuthority(
            c.gate.run,
            c.gate.plans,
            deps,
            c.gate.controls,
        )
