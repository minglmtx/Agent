"""Exact accounting, shared caps, one-way dispatch and proof-bound settlement.

Pure domain tests use reference fixtures, not real provider/recovery evidence.
They do not demonstrate durable multi-process reservation or send enforcement.
"""

from itertools import product
import json
from typing import cast, get_args

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.budget import (
    BudgetAuthorization,
    BudgetLimit,
    BudgetScope,
    Money,
)
from lab_generate_skill.domain.errors import (
    BudgetExceeded,
    DispatchAlreadyCommitted,
    EvidenceNotFound,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.generation import (
    OutcomeProof,
    RequestEvent,
    RequestIdentity,
    RequestRecord,
    RequestState,
)
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.lifecycle import ResourceOwner
from lab_generate_skill.domain.request_ledger import (
    BudgetSnapshot,
    ReserveEntry,
    dispatch_request,
    reserve_request,
    settle_request,
)


def ref(letter: str = "a") -> EvidenceRef:
    return EvidenceRef(
        uri="cas://sha256/" + letter * 64,
        sha256=letter * 64,
        size_bytes=0,
        media_type="application/json",
        content_schema="fixture/1",
        visibility="private",
        producer="test",
    )


@pytest.fixture
def scope() -> BudgetScope:
    authorization = BudgetAuthorization(
        authorization_id="authorization",
        authorization_ref=ref(),
        ceiling=Money(units=10),
        budgets=(
            BudgetLimit(budget_id="a", ceiling=Money(units=7)),
            BudgetLimit(budget_id="b", ceiling=Money(units=7)),
        ),
    )
    return BudgetScope(authorization=authorization, budget_id="a")


def request(
    name: str = "one", *, budget: str = "a", run: str = "run"
) -> RequestIdentity:
    return RequestIdentity(
        request_id=name,
        authorization_id="authorization",
        budget_id=budget,
        owner=ResourceOwner(
            run_id=run, owner_id="owner", job_id="job", worker_id="worker-" + name
        ),
        task=TaskIdentity(
            source_task_id="source-" + name,
            task_id="task-" + name,
            split="train",
            site="map",
            family="export",
            contract_version=1,
        ),
        candidate_index=0,
        revision_index=0,
        role="teacher",
        logical_index=0,
        provider_id="openrouter",
        model_id="fixture/model",
        input_sha256="a" * 64,
        parameters_sha256="b" * 64,
    )


def reserve(
    scope: BudgetScope, identity: RequestIdentity | None = None, units: int = 4
) -> BudgetSnapshot:
    identity = identity or request()
    snapshot, _ = reserve_request(
        BudgetSnapshot(authorization=scope.authorization),
        scope,
        identity,
        Money(units=units),
        "reserve-" + identity.request_id,
    )
    return snapshot


def dispatched(scope: BudgetScope) -> BudgetSnapshot:
    snapshot = reserve(scope)
    return dispatch_request(snapshot, snapshot.project()[0].reservation, 0, "dispatch")


def proof(
    identity: RequestIdentity,
    outcome: str,
    *,
    units: int = 2,
    evidence: EvidenceRef | None = None,
) -> OutcomeProof:
    data: dict[str, object] = {
        "request": identity,
        "outcome": outcome,
        "evidence": (evidence or ref(),),
    }
    if outcome in ("succeeded", "charged_failure"):
        data.update(
            charge=Money(units=units),
            response_ref=ref("c"),
            provider_request_id="provider-request",
        )
    elif outcome in ("released_not_dispatched", "rejected_before_execution"):
        data["charge"] = Money(units=0)
        if outcome == "released_not_dispatched":
            data["writer_termination_ref"] = ref("d")
    return OutcomeProof.model_validate(data)


@pytest.mark.parametrize(
    "units", [None, True, False, -1, 0.0, 1.0, "1", float("nan"), float("inf"), [], {}]
)
def test_money_rejects_wrong_type_negative_and_nonfinite(units: object) -> None:
    with pytest.raises(ValidationError):
        Money.model_validate({"units": units})


@pytest.mark.parametrize("units", [0, 1, 10**9, 10**100])
def test_exact_fixed_point_money_round_trip_without_overflow(units: int) -> None:
    money = Money(units=units)
    assert money.currency == "USD" and money.scale == 9
    assert Money.model_validate_json(money.model_dump_json()) == money
    assert money.units + 1 - money.units == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency", "EUR"),
        ("scale", 6),
        ("scale", 9.0),
        ("scale", "9"),
        ("schema_version", "money/2"),
        ("unexpected", 1),
    ],
)
def test_money_currency_precision_and_schema_are_explicit(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        Money.model_validate({"units": 1, field: value})


def test_shared_authorization_and_subbudget_limits_across_runs(
    scope: BudgetScope,
) -> None:
    first = reserve(scope, units=7)
    with pytest.raises(BudgetExceeded):
        reserve_request(
            first, scope, request("two", run="other-run"), Money(units=1), "reserve-two"
        )
    other = BudgetScope(authorization=scope.authorization, budget_id="b")
    exact, _ = reserve_request(
        first,
        other,
        request("two", budget="b", run="other-run"),
        Money(units=3),
        "reserve-two",
    )
    assert exact.held.units == 10
    with pytest.raises(BudgetExceeded):
        reserve_request(
            exact, other, request("three", budget="b"), Money(units=1), "reserve-three"
        )
    assert exact.charged.units == 0 and not exact.blocked


def test_reservation_replay_unchanged_and_changed_identity_refused(
    scope: BudgetScope,
) -> None:
    snapshot = reserve(scope)
    repeated, reservation = reserve_request(
        snapshot, scope, request(), Money(units=4), "inspect-reserve"
    )
    assert repeated is snapshot and reservation == snapshot.project()[0].reservation
    for field, value in (
        ("input_sha256", "f" * 64),
        ("parameters_sha256", "f" * 64),
        ("model_id", "other/model"),
    ):
        changed = RequestIdentity.model_validate(
            {**request().model_dump(), field: value}
        )
        with pytest.raises(OwnershipConflict):
            reserve_request(snapshot, scope, changed, Money(units=4), "changed")
    with pytest.raises(OwnershipConflict):
        reserve_request(snapshot, scope, request(), Money(units=3), "changed-ceiling")


def test_logical_call_cannot_gain_new_id_or_worker(scope: BudgetScope) -> None:
    snapshot = reserve(scope)
    identity = request()
    changed = RequestIdentity.model_validate(
        {
            **identity.model_dump(),
            "request_id": "new-id",
            "owner": {**identity.owner.model_dump(), "worker_id": "replacement"},
        }
    )
    with pytest.raises(OwnershipConflict):
        reserve_request(snapshot, scope, changed, Money(units=4), "reserve-new")
    assert snapshot.held.units == 4


@pytest.mark.parametrize("revision", [None, True, False, "0", 0.0, -1, [], {}])
def test_request_revision_strictly_typed(scope: BudgetScope, revision: object) -> None:
    snapshot = reserve(scope)
    with pytest.raises(ValueError):
        dispatch_request(
            snapshot, snapshot.project()[0].reservation, cast(int, revision), "dispatch"
        )


def test_dispatch_is_not_replayable_even_with_original_revision(
    scope: BudgetScope,
) -> None:
    snapshot = dispatched(scope)
    with pytest.raises(DispatchAlreadyCommitted):
        dispatch_request(snapshot, snapshot.project()[0].reservation, 0, "dispatch")
    with pytest.raises(DispatchAlreadyCommitted):
        dispatch_request(
            snapshot, snapshot.project()[0].reservation, 1, "different-send"
        )
    assert snapshot.held.units == 4 and snapshot.charged.units == 0


def test_uncertain_retains_hold_and_response_can_be_settled_without_resend(
    scope: BudgetScope,
) -> None:
    snapshot = dispatched(scope)
    unknown = OutcomeProof.model_validate(
        {
            **proof(request(), "uncertain").model_dump(),
            "response_ref": ref("c"),
            "provider_request_id": "provider-request",
        }
    )
    pending, receipt = settle_request(snapshot, request(), unknown, 1, "timeout")
    assert pending.held.units == 4 and pending.charged.units == 0
    assert receipt.record.state == "uncertain"
    with pytest.raises(DispatchAlreadyCommitted):
        dispatch_request(pending, pending.project()[0].reservation, 2, "resend")
    finished, paid = settle_request(
        pending, request(), proof(request(), "succeeded", units=3), 2, "settle"
    )
    assert finished.held.units == 0 and finished.charged.units == 3
    assert paid.record.events[-1].proof is not None
    assert paid.record.events[-1].proof.response_ref == unknown.response_ref
    assert sum(event.state == "dispatching" for event in paid.record.events) == 1


def test_actual_overage_recorded_and_blocks_reserve_and_existing_unsent_request(
    scope: BudgetScope,
) -> None:
    first = reserve(scope, units=4)
    other_scope = BudgetScope(authorization=scope.authorization, budget_id="b")
    both, other = reserve_request(
        first, other_scope, request("two", budget="b"), Money(units=3), "reserve-two"
    )
    sending = dispatch_request(both, both.project()[0].reservation, 0, "dispatch")
    paid, receipt = settle_request(
        sending, request(), proof(request(), "succeeded", units=11), 1, "settle"
    )
    assert receipt.record.charged.units == 11
    assert paid.charged.units == 11 and paid.held.units == 3 and paid.blocked
    with pytest.raises(BudgetExceeded):
        dispatch_request(paid, other, 0, "send-two")
    with pytest.raises(BudgetExceeded):
        reserve_request(
            paid,
            other_scope,
            request("three", budget="b"),
            Money(units=1),
            "reserve-three",
        )


def test_cost_correction_preserves_facts_and_original_settlement_receipt(
    scope: BudgetScope,
) -> None:
    initial = proof(request(), "succeeded", units=8)
    paid, receipt = settle_request(dispatched(scope), request(), initial, 1, "settle")
    correction = OutcomeProof(
        request=request(),
        outcome="charge_corrected",
        evidence=(ref("e"),),
        charge=Money(units=1),
        supersedes=initial.digest,
    )
    corrected, revised = settle_request(
        paid, request(), correction, 2, "correct-charge"
    )
    assert corrected.charged.units == 1 and corrected.held.units == 0
    assert corrected.blocked  # Original overage is not erased by a refund.
    assert revised.record.events[:-1] == receipt.record.events
    replay, original_receipt = settle_request(
        corrected, request(), initial, 1, "inspect-old"
    )
    assert replay is corrected and original_receipt == receipt
    replay, repeated_correction = settle_request(
        corrected, request(), correction, 2, "inspect-new"
    )
    assert replay is corrected and repeated_correction == revised


def test_release_requires_unissued_dispatch_and_rejection_releases_after_dispatch(
    scope: BudgetScope,
) -> None:
    reserved = reserve(scope)
    released, receipt = settle_request(
        reserved, request(), proof(request(), "released_not_dispatched"), 0, "release"
    )
    assert (
        released.held.units == 0 and receipt.record.state == "released_not_dispatched"
    )
    with pytest.raises(ValidationError):
        settle_request(
            dispatched(scope),
            request(),
            proof(request(), "released_not_dispatched"),
            1,
            "unsafe-release",
        )
    rejected, _ = settle_request(
        dispatched(scope),
        request(),
        proof(request(), "rejected_before_execution"),
        1,
        "reject",
    )
    assert rejected.held.units == rejected.charged.units == 0
    with pytest.raises(DispatchAlreadyCommitted):
        dispatch_request(
            rejected, rejected.project()[0].reservation, 2, "retry-rejected"
        )


@pytest.mark.parametrize(
    "outcome",
    [
        "succeeded",
        "charged_failure",
        "uncertain",
        "released_not_dispatched",
        "rejected_before_execution",
        "charge_corrected",
    ],
)
def test_missing_proof_fields_cannot_be_treated_as_settlement(outcome: str) -> None:
    with pytest.raises(ValidationError):
        OutcomeProof.model_validate(
            {"request": request(), "outcome": outcome, "evidence": ()}
        )


@pytest.mark.parametrize(
    "change",
    [
        {"charge": Money(units=0)},
        {"response_ref": ref("c")},
        {"writer_termination_ref": ref("d")},
    ],
)
def test_unknown_does_not_fabricate_free_cost_or_proof(
    change: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        OutcomeProof.model_validate(
            {**proof(request(), "uncertain").model_dump(), **change}
        )


def test_proof_identity_revision_and_correction_chain(scope: BudgetScope) -> None:
    snapshot = dispatched(scope)
    with pytest.raises(OwnershipConflict):
        settle_request(
            snapshot,
            request(),
            proof(request("other"), "succeeded"),
            1,
            "wrong-request",
        )
    with pytest.raises(RevisionConflict):
        settle_request(snapshot, request(), proof(request(), "succeeded"), 0, "stale")
    paid, receipt = settle_request(
        snapshot, request(), proof(request(), "succeeded"), 1, "settle"
    )
    with pytest.raises(ValidationError):
        settle_request(
            paid, request(), proof(request(), "succeeded", units=3), 2, "replace"
        )
    correction = OutcomeProof(
        request=request(),
        outcome="charge_corrected",
        evidence=(ref("e"),),
        charge=Money(units=3),
        supersedes="f" * 64,
    )
    with pytest.raises(ValidationError):
        settle_request(paid, request(), correction, 2, "wrong-parent")
    assert paid.project()[0] == receipt.record


STATES: tuple[RequestState, ...] = (
    "budget_reserved",
    "dispatching",
    "uncertain",
    "succeeded",
    "charged_failure",
    "rejected_before_execution",
    "released_not_dispatched",
)
EDGES = {
    ("budget_reserved", "dispatching"),
    ("budget_reserved", "released_not_dispatched"),
    ("dispatching", "uncertain"),
    ("dispatching", "succeeded"),
    ("dispatching", "charged_failure"),
    ("dispatching", "rejected_before_execution"),
    ("uncertain", "uncertain"),
    ("uncertain", "succeeded"),
    ("uncertain", "charged_failure"),
    ("uncertain", "rejected_before_execution"),
}


def test_state_matrix_covers_public_contract_without_deriving_expected_edges() -> None:
    # Keep STATES and EDGES independently specified above. get_args detects a
    # new public state; it must not generate the expected legal transition set.
    assert len(STATES) == len(set(STATES)) == 7
    assert set(STATES) == set(get_args(RequestState))
    assert len(tuple(product(STATES, STATES))) == 49


@pytest.mark.parametrize(("before", "after"), list(product(STATES, STATES)))
def test_request_transition_matrix(
    scope: BudgetScope, before: RequestState, after: RequestState
) -> None:
    snapshot = reserve(scope)
    if before not in ("budget_reserved", "released_not_dispatched"):
        snapshot = dispatch_request(
            snapshot, snapshot.project()[0].reservation, 0, "dispatch"
        )
    if before not in ("budget_reserved", "dispatching"):
        snapshot, _ = settle_request(
            snapshot,
            request(),
            proof(request(), before),
            snapshot.project()[0].revision,
            "outcome",
        )
    record = snapshot.project()[0]
    event = RequestEvent(
        operation_id="next",
        state=after,
        proof=(
            None
            if after in ("budget_reserved", "dispatching")
            else proof(request(), after, evidence=ref("e"))
        ),
    )
    if (before, after) in EDGES:
        assert (
            RequestRecord(
                reservation=record.reservation, events=(*record.events, event)
            ).state
            == after
        )
    else:
        with pytest.raises(ValidationError):
            RequestRecord(
                reservation=record.reservation, events=(*record.events, event)
            )


def test_snapshot_validates_historical_caps_not_only_final_total(
    scope: BudgetScope,
) -> None:
    one = reserve(scope, units=7)
    other_scope = BudgetScope(authorization=scope.authorization, budget_id="b")
    other = reserve(other_scope, request("two", budget="b"), units=7)
    with pytest.raises(ValidationError, match="shared authorization"):
        BudgetSnapshot(
            authorization=scope.authorization, entries=(*one.entries, *other.entries)
        )
    assert BudgetSnapshot.model_validate_json(one.model_dump_json()) == one


@pytest.mark.parametrize(
    "budgets",
    [
        (),
        None,
        [],
        (BudgetLimit(budget_id="a", ceiling=Money(units=11)),),
        (
            BudgetLimit(budget_id="a", ceiling=Money(units=1)),
            BudgetLimit(budget_id="a", ceiling=Money(units=1)),
        ),
    ],
)
def test_authorization_rejects_empty_wrong_duplicate_or_oversized_budgets(
    scope: BudgetScope, budgets: object
) -> None:
    with pytest.raises(ValidationError):
        BudgetAuthorization.model_validate(
            {**scope.authorization.model_dump(), "budgets": budgets}
        )


def test_empty_authorized_ledger_and_missing_request(scope: BudgetScope) -> None:
    snapshot = BudgetSnapshot(authorization=scope.authorization)
    assert snapshot.charged.units == snapshot.held.units == snapshot.revision == 0
    assert not snapshot.blocked
    with pytest.raises(EvidenceNotFound):
        settle_request(snapshot, request(), proof(request(), "succeeded"), 0, "settle")


def test_inflating_authorization_or_zero_reservation_is_rejected(
    scope: BudgetScope,
) -> None:
    snapshot = reserve(scope)
    altered = BudgetAuthorization.model_validate(
        {**scope.authorization.model_dump(), "ceiling": Money(units=100)}
    )
    with pytest.raises(OwnershipConflict):
        reserve_request(
            snapshot,
            BudgetScope(authorization=altered, budget_id="a"),
            request("two"),
            Money(units=1),
            "more-budget",
        )
    with pytest.raises(ValidationError):
        reserve_request(snapshot, scope, request("two"), Money(units=0), "zero")


def test_operation_id_scope_and_duplicate_reservation_records(
    scope: BudgetScope,
) -> None:
    first = reserve(scope, units=2)
    _, second = reserve_request(
        first, scope, request("two"), Money(units=2), "reserve-two"
    )
    with pytest.raises(ValidationError, match="Operation ID"):
        BudgetSnapshot(
            authorization=scope.authorization,
            entries=(
                *first.entries,
                ReserveEntry(operation_id="reserve-one", reservation=second),
            ),
        )
    with pytest.raises(ValidationError, match="reserve only once"):
        BudgetSnapshot(
            authorization=scope.authorization, entries=(*first.entries, *first.entries)
        )


@pytest.mark.parametrize("scale", [9.0, "9", True, None, [], {}, 8, 10])
def test_json_precision_rejects_wrong_types_and_values(scale: object) -> None:
    with pytest.raises(ValidationError):
        Money.model_validate_json(json.dumps({"units": 1, "scale": scale}))


def test_explicit_integer_precision_works_in_both_input_formats() -> None:
    expected = Money(units=1)
    assert Money.model_validate({"units": 1, "scale": 9}) == expected
    assert Money.model_validate_json('{"units":1,"scale":9}') == expected


@pytest.mark.parametrize(
    "outcome,field,value",
    [
        ("succeeded", "response_ref", None),
        ("succeeded", "provider_request_id", None),
        ("succeeded", "charge", None),
        ("released_not_dispatched", "writer_termination_ref", None),
        ("released_not_dispatched", "charge", Money(units=1)),
        ("rejected_before_execution", "charge", Money(units=1)),
        ("rejected_before_execution", "response_ref", ref("c")),
    ],
)
def test_nonempty_evidence_does_not_replace_required_outcome_facts(
    outcome: str, field: str, value: object
) -> None:
    data = proof(request(), outcome).model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        OutcomeProof.model_validate(data)


def test_original_owner_and_subbudget_cannot_change_during_dispatch(
    scope: BudgetScope,
) -> None:
    snapshot = reserve(scope)
    original = snapshot.project()[0].reservation
    changed_request = RequestIdentity.model_validate(
        {
            **original.request.model_dump(),
            "owner": {**original.request.owner.model_dump(), "owner_id": "other"},
        }
    )
    changed_reservation = type(original).model_validate(
        {**original.model_dump(), "request": changed_request}
    )
    with pytest.raises(OwnershipConflict):
        dispatch_request(snapshot, changed_reservation, 0, "takeover")
    with pytest.raises(ValidationError):
        BudgetScope(authorization=scope.authorization, budget_id="missing")
    assert snapshot.held.units == 4


def test_billing_adjustment_keeps_non_execution_outcome_but_records_fee(
    scope: BudgetScope,
) -> None:
    rejected_proof = proof(request(), "rejected_before_execution")
    rejected, receipt = settle_request(
        dispatched(scope), request(), rejected_proof, 1, "reject"
    )
    correction = OutcomeProof(
        request=request(),
        outcome="charge_corrected",
        evidence=(ref("e"),),
        charge=Money(units=1),
        supersedes=rejected_proof.digest,
    )
    updated, adjusted = settle_request(
        rejected, request(), correction, 2, "billing-fee"
    )
    assert adjusted.record.state == receipt.record.state == "rejected_before_execution"
    assert updated.charged.units == 1 and updated.held.units == 0
    assert adjusted.record.events[: len(receipt.record.events)] == receipt.record.events


@pytest.mark.parametrize("unknown_count", [0, 1, 2])
@pytest.mark.parametrize("charge", [0, 2, 5])
def test_charged_failure_sequence_replay_recovery_and_correction(
    scope: BudgetScope, unknown_count: int, charge: int
) -> None:
    snapshot = dispatched(scope)
    for index in range(unknown_count):
        unknown = proof(request(), "uncertain", evidence=ref("ab"[index]))
        snapshot, _ = settle_request(
            snapshot,
            request(),
            unknown,
            snapshot.project()[0].revision,
            "unknown-" + str(index),
        )
        assert snapshot.project()[0].held.units == 4
    failed = proof(request(), "charged_failure", units=charge)
    failed_revision = snapshot.project()[0].revision
    snapshot, receipt = settle_request(
        snapshot,
        request(),
        failed,
        failed_revision,
        "failed-charge",
    )
    original = snapshot
    snapshot = BudgetSnapshot.model_validate_json(snapshot.model_dump_json())
    assert snapshot == original
    assert snapshot.project()[0].state == "charged_failure"
    assert snapshot.charged.units == charge and snapshot.held.units == 0
    assert snapshot.blocked == (charge > 4)
    # A lost acknowledgement/restarted caller recovers the original receipt.
    repeated, recovered = settle_request(
        snapshot,
        request(),
        failed,
        failed_revision,
        "recover-original",
    )
    assert repeated == snapshot and recovered == receipt
    with pytest.raises(DispatchAlreadyCommitted):
        dispatch_request(
            snapshot, receipt.record.reservation, receipt.record.revision, "resend"
        )
    with pytest.raises(ValidationError):
        settle_request(
            snapshot,
            request(),
            proof(request(), "succeeded"),
            receipt.record.revision,
            "turn-success",
        )
    with pytest.raises(ValidationError):
        settle_request(
            snapshot,
            request(),
            proof(request(), "charged_failure", units=charge + 1),
            receipt.record.revision,
            "replace-failure",
        )
    correction = OutcomeProof(
        request=request(),
        outcome="charge_corrected",
        evidence=(ref("e"),),
        charge=Money(units=1),
        supersedes=failed.digest,
    )
    with pytest.raises(ValidationError):
        settle_request(
            snapshot,
            request(),
            correction.model_copy(update={"supersedes": "f" * 64}),
            receipt.record.revision,
            "wrong-chain",
        )
    corrected, adjusted = settle_request(
        snapshot, request(), correction, receipt.record.revision, "correct-charge"
    )
    assert adjusted.record.state == "charged_failure"
    assert corrected.charged.units == 1 and corrected.held.units == 0
    assert corrected.entries[: len(snapshot.entries)] == snapshot.entries
    assert corrected.blocked == (charge > 4)  # Refund cannot erase an incident.
    assert settle_request(
        corrected, request(), correction, receipt.record.revision, "repeat-correction"
    ) == (corrected, adjusted)
    assert settle_request(
        corrected, request(), failed, failed_revision, "recover-old-receipt"
    ) == (corrected, receipt)
    with pytest.raises(DispatchAlreadyCommitted):
        dispatch_request(
            corrected,
            adjusted.record.reservation,
            adjusted.record.revision,
            "resend-after-correction",
        )
    assert snapshot == original
