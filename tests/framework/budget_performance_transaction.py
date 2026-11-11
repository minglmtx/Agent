"""Instrument actual synthetic FileRequestLedger operations on workspace storage.

Times are inclusive: load includes capacity, whole operation includes everything.
No real authority, provider traffic or production ledger is used or touched.
"""

from multiprocessing import get_context
from multiprocessing.connection import Connection
from pathlib import Path
from time import perf_counter
import fcntl
import os

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.request_ledger import FileRequestLedger
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.budget import BudgetAuthorization, BudgetScope, Money
from lab_generate_skill.domain.budget_journal import BudgetJournalSnapshot
from lab_generate_skill.domain.generation import RequestIdentity
from lab_generate_skill.domain.request_ledger import BudgetSnapshot
from lab_generate_skill.runtime.lifecycle import OperationGuards
from budget_capacity_fixtures import snapshot
from budget_performance_timing import timings
from test_file_request_ledger import NoCancel, UnitAuthority, Harness, operation, put
from test_request_budget import request


def hold_lock(path: str, ready: Connection) -> None:
    with open(path, "rb") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        ready.send("locked")
        if ready.recv() != "measure":
            raise ValueError("Unexpected contention command")
        # Deliberate bounded contention, not an assertion about filesystem speed.
        import time

        time.sleep(0.2)
    ready.close()


def reopen(
    root: str, auth: str, limits: str, identity: str, output: Connection
) -> None:
    from lab_generate_skill.domain.budget_journal import BudgetJournalCapacity
    from lab_generate_skill.domain.budget_policy import BudgetDispatchPolicy

    path = Path(root)
    store = FileEvidenceStore(path / "evidence")
    owner = RequestIdentity.model_validate_json(identity)
    with timings() as result:
        start = perf_counter()
        ledger = FileRequestLedger(
            path / "ledger",
            BudgetAuthorization.model_validate_json(auth),
            BudgetJournalCapacity.model_validate_json(limits),
            OperationGuards(SystemClock(), NoCancel()),
            store,
            UnitAuthority(store),
            dispatch_policy=BudgetDispatchPolicy(max_unsettled_dispatches=1),
        )
        record = ledger.read(owner, operation(owner, seconds=120))
        result["reopen_total_seconds"] = perf_counter() - start
        output.send(
            {
                "timing": result,
                "state": record.state,
                "charged": record.charged.units,
                "pid": os.getpid(),
            }
        )
    output.close()


def measure_transactions(root: Path, count: int) -> dict[str, object]:
    root.mkdir()
    (root / "evidence").mkdir()
    (root / "ledger").mkdir()
    store = FileEvidenceStore(root / "evidence")
    seed = snapshot(count)
    auth = seed.history.authorization.model_copy(
        update={"authorization_ref": put(store, {"unit_authorization": True})}
    )
    scope = BudgetScope(authorization=auth, budget_id="a")
    entries = []
    for entry in seed.history.entries:
        from lab_generate_skill.domain.request_ledger import ReserveEntry

        assert isinstance(entry, ReserveEntry)
        entries.append(
            entry.model_copy(
                update={
                    "reservation": entry.reservation.model_copy(update={"scope": scope})
                }
            )
        )
    seed = BudgetJournalSnapshot(
        capacity=seed.capacity,
        dispatch_policy=seed.dispatch_policy,
        history=BudgetSnapshot(authorization=auth, entries=tuple(entries)),
        operations=seed.operations,
    )
    seed.check_capacity()
    controls = OperationGuards(SystemClock(), NoCancel())
    harness = Harness(root, store, scope, UnitAuthority(store))
    ledger = FileRequestLedger(
        root / "ledger",
        auth,
        seed.capacity,
        controls,
        store,
        harness.authority,
        dispatch_policy=seed.dispatch_policy,
    )
    identity = request("measured-new")
    # Seed a validated synthetic retained history; measured mutations below use
    # the public ledger path, including its real CAS, marker, lock and fsync.
    with ledger._file.locked(
        controls.bind(operation(identity, seconds=120))
    ) as transaction:
        transaction.write(seed.model_dump_json().encode())
    rows: dict[str, object] = {}
    with timings() as values:
        start = perf_counter()
        reservation = ledger.reserve(
            scope, identity, Money(units=4), operation(identity, seconds=120)
        )
        rows["reserve"] = {**values, "total_seconds": perf_counter() - start}
    with timings() as values:
        start = perf_counter()
        ledger.mark_dispatching(reservation, 0, operation(identity, seconds=120))
        rows["dispatch"] = {**values, "total_seconds": perf_counter() - start}
    proof = harness.proof(identity)
    with timings() as values:
        start = perf_counter()
        result = ledger.settle(identity, proof, 1, operation(identity, seconds=120))
        rows["settle"] = {**values, "total_seconds": perf_counter() - start}
    assert result.record.state == "succeeded" and result.record.charged.units == 2
    context = get_context("spawn")
    parent, child = context.Pipe()
    holder = context.Process(
        target=hold_lock, args=(str(harness.path) + ".lock", child)
    )
    holder.start()
    try:
        if not parent.poll(20) or parent.recv() != "locked":
            raise RuntimeError("Contention worker not ready")
        parent.send("measure")
        with timings() as values:
            start = perf_counter()
            assert (
                ledger.read(identity, operation(identity, seconds=120)) == result.record
            )
            rows["contended_read"] = {**values, "total_seconds": perf_counter() - start}
        holder.join(20)
        assert holder.exitcode == 0
    finally:
        if holder.is_alive():
            holder.kill()
            holder.join(5)
        parent.close()
        child.close()
    parent, child = context.Pipe()
    reader = context.Process(
        target=reopen,
        args=(
            str(root),
            auth.model_dump_json(),
            seed.capacity.model_dump_json(),
            identity.model_dump_json(),
            child,
        ),
    )
    reader.start()
    try:
        if not parent.poll(120):
            raise TimeoutError("New-process recovery exceeded its bound")
        recovered = parent.recv()
        reader.join(20)
        assert (
            reader.exitcode == 0
            and recovered["state"] == "succeeded"
            and recovered["charged"] == 2
        )
        rows["new_process_readback"] = recovered
    finally:
        if reader.is_alive():
            reader.kill()
            reader.join(5)
        parent.close()
        child.close()
    persisted = BudgetJournalSnapshot.model_validate_json(harness.path.read_bytes())
    persisted.check_capacity()
    assert len(persisted.history.project()) == count + 1
    assert (
        persisted.history.charged.units == 2
        and persisted.history.held.units == count * 4
    )
    return {
        "operations": rows,
        "final_bytes": harness.path.stat().st_size,
        "requests": count + 1,
    }
