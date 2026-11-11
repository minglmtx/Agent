"""Durable pre-send fence: missing diagnostics cannot reopen shared spending."""

import multiprocessing
import os
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.budget_policy import BudgetDispatchPolicy
from lab_generate_skill.domain.budget_journal import BudgetReconciliationRequired
from lab_generate_skill.domain.errors import (
    BudgetExceeded,
    DispatchAlreadyCommitted,
    EvidenceIntegrityError,
)
from lab_generate_skill.domain.budget import Money, BudgetAuthorization, BudgetScope
from lab_generate_skill.domain.generation import OutcomeProof
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from test_file_request_ledger import (
    Harness,
    UnitAuthority,
    harness as harness,
    operation,
)
from test_request_budget import request
from test_run_plan import plan as run_plan


@pytest.mark.parametrize("value", [None, True, False, 0, 2, -1, 1.0, "1"])
def test_dispatch_policy_explicit_strict_and_no_implicit_parallelism(
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        BudgetDispatchPolicy.model_validate({"max_unsettled_dispatches": value})
    with pytest.raises(ValidationError):
        BudgetDispatchPolicy.model_validate({})


def test_unknown_fences_all_workers_until_original_terminal_proof(
    harness: Harness,
) -> None:
    a, b, c = (
        request(),
        request("b", budget="b", run="other"),
        request("c", budget="b", run="third"),
    )
    ledger = harness.ledger()
    first = harness.reserve(a, units=4)
    second = harness.reserve(b, units=2)
    ledger.mark_dispatching(first, 0, operation(a))
    for observe_unknown in (False, True):
        if observe_unknown:
            ledger.settle(a, harness.proof(a, "uncertain"), 1, operation(a))
        saved = harness.path.read_bytes()
        with pytest.raises(BudgetReconciliationRequired):
            harness.reserve(c, units=1)
        with pytest.raises(BudgetReconciliationRequired):
            harness.ledger().mark_dispatching(second, 0, operation(b))
        with pytest.raises(DispatchAlreadyCommitted):
            harness.ledger().mark_dispatching(first, 0, operation(a))
        assert harness.path.read_bytes() == saved
        assert (
            harness.reserve(a, units=4) == first
        )  # Diagnostic reserve replay is no permit.
    proof = harness.proof(a, "charged_failure", units=2)
    receipt = ledger.settle(a, proof, 2, operation(a))
    assert receipt.record.state == "charged_failure" and receipt.record.held.units == 0
    assert harness.ledger().settle(a, proof, 2, operation(a)) == receipt
    assert harness.ledger().mark_dispatching(second, 0, operation(b)).request == b


def test_failed_charge_overage_and_correction_keep_incident(harness: Harness) -> None:
    a = request()
    ledger = harness.ledger()
    reservation = harness.reserve(a)
    ledger.mark_dispatching(reservation, 0, operation(a))
    original = harness.proof(a, "charged_failure", units=9)
    receipt = ledger.settle(a, original, 1, operation(a))
    assert receipt.record.exceeded_reservation
    correction = harness.proof(
        a, "charge_corrected", units=1, supersedes=original.digest
    )
    updated = ledger.settle(a, correction, 2, operation(a))
    assert (
        updated.record.state == "charged_failure" and updated.record.charged.units == 1
    )
    assert updated.record.exceeded_reservation
    with pytest.raises(BudgetExceeded):
        harness.reserve(request("next", budget="b"), units=1)


def test_old_plan_and_budget_snapshot_require_explicit_migration(
    harness: Harness,
) -> None:
    plan = run_plan()
    assert plan.schema_version == "run-plan/3" and plan.budget is not None
    assert plan.budget.dispatch_policy.max_unsettled_dispatches == 1
    with pytest.raises(ValidationError):
        type(plan).model_validate(
            plan.model_copy(update={"schema_version": "run-plan/1"})
        )
    harness.reserve()
    raw = harness.path.read_bytes().replace(
        b'"budget-journal-snapshot/2"', b'"budget-journal-snapshot/1"'
    )
    harness.path.write_bytes(raw)
    with pytest.raises(EvidenceIntegrityError):
        harness.ledger().read(request(), operation(request()))
    assert harness.path.read_bytes() == raw


def crash(root: str, authorization: str) -> None:
    path = Path(root)
    auth = BudgetAuthorization.model_validate_json(authorization)
    store = FileEvidenceStore(path / "evidence")
    h = Harness(
        path,
        store,
        BudgetScope(authorization=auth, budget_id="a"),
        UnitAuthority(store),
    )
    reservation = h.reserve()
    h.ledger().mark_dispatching(reservation, 0, operation(request()))
    os._exit(23)  # No response or failure diagnostic ever written.


def contender(root: str, authorization: str, queue: Any) -> None:
    path = Path(root)
    auth = BudgetAuthorization.model_validate_json(authorization)
    store = FileEvidenceStore(path / "evidence")
    h = Harness(
        path,
        store,
        BudgetScope(authorization=auth, budget_id="a"),
        UnitAuthority(store),
    )
    try:
        h.reserve(request("other", budget="b", run="other"), units=1)
    except BudgetReconciliationRequired:
        queue.put("blocked")
    else:
        queue.put("unexpected_send_opportunity")


def test_new_process_blocks_different_run_after_writer_dies_before_diagnostic(
    harness: Harness,
) -> None:
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    args = (str(harness.root), harness.scope.authorization.model_dump_json())
    original = ctx.Process(target=crash, args=args)
    current = ctx.Process(target=contender, args=(*args, queue))
    try:
        original.start()
        original.join(20)
        assert not original.is_alive() and original.exitcode == 23
        current.start()
        current.join(20)
        assert not current.is_alive() and current.exitcode == 0
        assert queue.get(timeout=3) == "blocked"
        assert (
            harness.ledger().read(request(), operation(request())).state
            == "dispatching"
        )
    finally:
        for process in (original, current):
            if process.is_alive():
                process.kill()
                process.join(5)
        queue.close()
        queue.join_thread()


@pytest.mark.parametrize("charge", [None, True, -1, "0"])
def test_charged_failure_requires_exact_amount_and_original_response(
    harness: Harness, charge: object
) -> None:
    proof = harness.proof(request(), "charged_failure", units=0)
    with pytest.raises(ValidationError):
        OutcomeProof.model_validate(proof.model_copy(update={"charge": charge}))
    with pytest.raises(ValidationError):
        OutcomeProof.model_validate(proof.model_copy(update={"response_ref": None}))
