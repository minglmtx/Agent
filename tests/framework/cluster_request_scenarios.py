"""Two-rank storage integration scenarios; explicit unit authority, no provider.

Inputs are a fresh shared output root and rank 0/1. Each independent scenario
has its own fixture authorization, but both ranks use the same ledger root.
Return values describe observed outcomes; unexpected exceptions fail the job.
Synchronization is bounded and its files remain as evidence, not runtime APIs.
"""

import json
import os
import socket
import time
from pathlib import Path
from typing import Callable

from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.budget import (
    BudgetAuthorization,
    BudgetLimit,
    BudgetScope,
    Money,
)
from lab_generate_skill.domain.budget_journal import (
    BudgetJournalSnapshot,
    BudgetReconciliationRequired,
    SettlementPending,
)
from lab_generate_skill.domain.errors import (
    BudgetExceeded,
    DispatchAlreadyCommitted,
    JournalCapacityExceeded,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.generation import OutcomeProof, RequestIdentity
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards

from test_file_request_ledger import (
    Harness,
    NoCancel,
    UnitAuthority,
    capacity,
    operation,
    put,
)
from test_request_budget import request


def publish(path: Path, value: object) -> None:
    """Publish a uniquely owned fixture record; never replace prior evidence."""
    temporary = path.with_name(path.name + ".writing")
    if path.exists():
        raise FileExistsError(path)
    with temporary.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.rename(temporary, path)


def wait_for(path: Path, seconds: float = 60) -> None:
    deadline = time.monotonic() + seconds
    while not path.is_file():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Peer did not publish {path.name}")
        time.sleep(0.05)


def barrier(root: Path, name: str, rank: int) -> None:
    publish(
        root / f"{name}-{rank}.json",
        {"rank": rank, "node": socket.gethostname(), "time_ns": time.time_ns()},
    )
    wait_for(root / f"{name}-{1-rank}.json")


def identity(
    phase: str, name: str = "one", *, budget: str = "a", run: str = "run"
) -> RequestIdentity:
    fields = request(name, budget=budget, run=run).model_dump(mode="python")
    fields["authorization_id"] = "cluster-fixture-" + phase
    return RequestIdentity.model_validate(fields)


def prepare(root: Path) -> None:
    (root / "evidence").mkdir()
    (root / "ledger").mkdir()
    store = FileEvidenceStore(root / "evidence")
    for phase in ("budget", "dispatch", "fence"):
        authorization = BudgetAuthorization(
            authorization_id="cluster-fixture-" + phase,
            authorization_ref=put(store, {"unit_authorization": True}),
            ceiling=Money(units=10),
            budgets=(
                BudgetLimit(budget_id="a", ceiling=Money(units=7)),
                BudgetLimit(budget_id="b", ceiling=Money(units=7)),
            ),
        )
        publish(
            root / f"{phase}-authorization.json", authorization.model_dump(mode="json")
        )


def case(root: Path, phase: str) -> Harness:
    authorization = BudgetAuthorization.model_validate_json(
        (root / f"{phase}-authorization.json").read_bytes()
    )
    store = FileEvidenceStore(root / "evidence")
    return Harness(
        root,
        store,
        BudgetScope(authorization=authorization, budget_id="a"),
        UnitAuthority(store),
    )


def expect(error: type[Exception], call: Callable[[], object]) -> str:
    try:
        call()
    except error:
        return error.__name__
    raise AssertionError(f"Expected {error.__name__}")


def lock_scenario(root: Path, rank: int) -> str:
    """Force a remote contender to time out while the other node holds flock."""
    file = AtomicSnapshotFile(
        root / "ledger", "f" * 64 + ".lock-test.json", max_bytes=1024
    )
    guards = OperationGuards(SystemClock(), NoCancel())
    if rank == 0:
        with file.locked(guards.bind(operation(identity("lock")))):
            publish(root / "lock-held.json", {"rank": rank})
            wait_for(root / "lock-timeout.json")
        publish(root / "lock-released.json", {"rank": rank})
        return "held_until_remote_timeout"
    wait_for(root / "lock-held.json")
    try:
        with file.locked(guards.bind(operation(identity("lock"), seconds=0.3))):
            raise AssertionError("Remote lock was entered while rank zero held it")
    except OperationStopped:
        publish(root / "lock-timeout.json", {"rank": rank})
    wait_for(root / "lock-released.json")
    with file.locked(guards.bind(operation(identity("lock")))) as transaction:
        assert transaction.read() is None
    return "timed_out_then_acquired"


def budget_scenario(root: Path, rank: int) -> str:
    harness = case(root, "budget")
    candidate = identity(
        "budget", f"race-{rank}", budget="a" if rank == 0 else "b", run=f"run-{rank}"
    )
    barrier(root, "budget-ready", rank)
    try:
        harness.reserve(candidate, units=7)
        result = "reserved"
    except BudgetExceeded:
        result = "BudgetExceeded"
    barrier(root, "budget-finished", rank)
    return result


def dispatch_scenario(root: Path, rank: int) -> str:
    harness = case(root, "dispatch")
    candidate = identity("dispatch")
    if rank == 0:
        harness.reserve(candidate)
    barrier(root, "dispatch-ready", rank)
    ledger = harness.ledger()
    reservation = ledger.read(candidate, operation(candidate)).reservation
    barrier(root, "dispatch-read", rank)
    try:
        permit = ledger.mark_dispatching(reservation, 0, operation(candidate))
        assert permit.request == candidate
        result = "permit"
    except DispatchAlreadyCommitted:
        result = "DispatchAlreadyCommitted"
    barrier(root, "dispatch-finished", rank)
    return result


def fence_scenario(root: Path, rank: int) -> str:
    harness = case(root, "fence")
    ledger = harness.ledger(limits=capacity(max_requests=2, max_entries=8))
    first = identity("fence")
    second = identity("fence", "second", budget="b", run="other")
    if rank == 0:
        reservation = harness.reserve(first, ledger=ledger)
        harness.reserve(second, ledger=ledger, units=2)
        ledger.mark_dispatching(reservation, 0, operation(first))
        ledger.settle(first, harness.proof(first, "uncertain"), 1, operation(first))
        paid = harness.proof(first)
        ledger.settle(first, paid, 2, operation(first))
        correction = harness.proof(
            first, "charge_corrected", units=3, supersedes=paid.digest
        )
        try:
            ledger.settle(first, correction, 3, operation(first))
        except SettlementPending as error:
            assert isinstance(error.__cause__, JournalCapacityExceeded)
            assert error.proof_ref.sha256 == correction.digest
            publish(
                root / "pending-proof.json", error.proof_ref.model_dump(mode="json")
            )
        else:
            raise AssertionError("Full journal unexpectedly accepted correction")
        wait_for(root / "fence-reconciled.json")
        assert ledger.read(first, operation(first)).charged.units == 3
        expect(
            DispatchAlreadyCommitted,
            lambda: ledger.mark_dispatching(reservation, 0, operation(first)),
        )
        return "pending_observed_remote_reconciliation"
    wait_for(root / "pending-proof.json")
    before = harness.path.read_bytes()
    second_record = ledger.read(second, operation(second))
    expect(
        BudgetReconciliationRequired,
        lambda: ledger.mark_dispatching(
            second_record.reservation, 0, operation(second)
        ),
    )
    expect(
        BudgetReconciliationRequired,
        lambda: harness.reserve(
            identity("fence", "third", budget="b", run="third"), ledger=ledger, units=1
        ),
    )
    assert harness.path.read_bytes() == before
    reference = EvidenceRef.model_validate_json(
        (root / "pending-proof.json").read_bytes()
    )
    proof = OutcomeProof.model_validate_json(harness.store.read(reference))
    assert proof.digest == reference.sha256
    ledger.settle(
        second,
        harness.proof(second, "released_not_dispatched", units=0),
        0,
        operation(second, cleanup=True),
    )
    assert len(list((root / "ledger").glob("*.pending-*"))) == 1
    receipt = ledger.settle(first, proof, 3, operation(first))
    assert receipt.record.charged.units == 3
    assert not list((root / "ledger").glob("*.pending-*"))
    committed = harness.path.read_bytes()
    assert ledger.settle(first, proof, 3, operation(first)) == receipt
    assert harness.path.read_bytes() == committed
    publish(
        root / "fence-reconciled.json",
        {"charge": 3, "duplicate_charge": False, "dispatch_and_reserve_blocked": True},
    )
    return "blocked_then_reconciled_once"


def verify_snapshots(root: Path) -> None:
    for phase, entries, held, charged in (
        ("budget", 1, 7, 0),
        ("dispatch", 2, 4, 0),
        ("fence", 7, 0, 3),
    ):
        snapshot = BudgetJournalSnapshot.model_validate_json(
            case(root, phase).path.read_bytes()
        )
        snapshot.check_capacity()
        assert len(snapshot.history.entries) == entries
        records = snapshot.history.project()
        assert sum(record.held.units for record in records) == held
        assert sum(record.charged.units for record in records) == charged
    assert not list((root / "ledger").glob("*.pending-*"))
