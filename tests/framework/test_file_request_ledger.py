"""Real shared-filesystem budget transactions; authority is a strict unit fixture.

These tests never call a provider. The fixture validates stored bindings, not
real user grants/claim ownership or provider authenticity; those are separate
integration gates before any paid send.
"""

import fcntl
import hashlib
import json
import multiprocessing
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.request_ledger import FileRequestLedger
from lab_generate_skill.domain.budget_policy import BudgetDispatchPolicy
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.budget import (
    BudgetAuthorization,
    BudgetLimit,
    BudgetScope,
    Money,
)
from lab_generate_skill.domain.budget_journal import (
    BudgetJournalCapacity,
    BudgetJournalSnapshot,
    SettlementPending,
    BudgetReconciliationRequired,
)
from lab_generate_skill.domain.errors import (
    BudgetExceeded,
    DispatchAlreadyCommitted,
    EvidenceIntegrityError,
    EvidenceNotFound,
    JournalCapacityExceeded,
    OperationStopped,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.generation import (
    OutcomeProof,
    RequestIdentity,
    RequestRecord,
    Reservation,
)
from lab_generate_skill.domain.lifecycle import CancellationRef, OperationContext
from lab_generate_skill.ports.requests import RequestLedger
from lab_generate_skill.runtime.lifecycle import OperationGuards

from test_request_budget import request


class NoCancel:
    def is_cancelled(self, reference: CancellationRef) -> bool:
        return False


def put(store: FileEvidenceStore, data: object) -> EvidenceRef:
    return store.put(
        json.dumps(data, sort_keys=True).encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="unit-request-fact/1",
            visibility="private",
            producer="unit-fixture",
        ),
    )


class UnitAuthority:
    """Explicit test-only authority; never installed by production bootstrap."""

    def __init__(self, store: FileEvidenceStore) -> None:
        self.store = store
        self.denied = False

    def authorize_reservation(
        self, reservation: Reservation, op: OperationContext
    ) -> None:
        if self.denied or json.loads(
            self.store.read(reservation.scope.authorization.authorization_ref)
        ) != {"unit_authorization": True}:
            raise OwnershipConflict("unit authority rejected reservation")

    def authorize_dispatch(self, record: RequestRecord, op: OperationContext) -> None:
        self.authorize_reservation(record.reservation, op)

    def verify_outcome(
        self, record: RequestRecord, proof: OutcomeProof, op: OperationContext
    ) -> None:
        if self.denied:
            raise OwnershipConflict("unit authority rejected proof")
        expected = {
            "request": proof.request.model_dump(mode="json"),
            "outcome": proof.outcome,
            "charge": None if proof.charge is None else proof.charge.units,
        }
        if json.loads(self.store.read(proof.evidence[0])) != expected:
            raise OwnershipConflict(
                "unit evidence did not bind exact request/outcome/charge"
            )
        if proof.outcome == "released_not_dispatched":
            assert proof.writer_termination_ref is not None
            if record.state != "budget_reserved" or json.loads(
                self.store.read(proof.writer_termination_ref)
            ) != {"ended": True, "owner": proof.request.owner.model_dump(mode="json")}:
                raise OwnershipConflict("unit release lacks exact writer proof")


def capacity(**changes: int) -> BudgetJournalCapacity:
    values = dict(
        max_requests=8, max_entries=100, max_bytes=1024 * 1024, max_entry_bytes=8192
    )
    values.update(changes)
    return BudgetJournalCapacity.model_validate(values)


def operation(
    identity: RequestIdentity, *, cleanup: bool = False, seconds: float = 30
) -> OperationContext:
    return OperationContext(
        operation_id="op-" + uuid4().hex,
        run_id=identity.owner.run_id,
        owner_id=identity.owner.owner_id,
        attempt_id=identity.attempt_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=seconds),
        mode="cleanup" if cleanup else "execute",
        parent_operation_id="original" if cleanup else None,
    )


@dataclass
class Harness:
    root: Path
    store: FileEvidenceStore
    scope: BudgetScope
    authority: UnitAuthority

    def ledger(
        self,
        *,
        limits: BudgetJournalCapacity | None = None,
        authorization: BudgetAuthorization | None = None,
    ) -> RequestLedger:
        return FileRequestLedger(
            self.root / "ledger",
            authorization or self.scope.authorization,
            limits or capacity(),
            OperationGuards(SystemClock(), NoCancel()),
            self.store,
            self.authority,
            dispatch_policy=BudgetDispatchPolicy(max_unsettled_dispatches=1),
        )

    @property
    def path(self) -> Path:
        return (
            self.root
            / "ledger"
            / (
                hashlib.sha256(
                    self.scope.authorization.authorization_id.encode()
                ).hexdigest()
                + ".requests.json"
            )
        )

    def reserve(
        self,
        identity: RequestIdentity | None = None,
        *,
        ledger: RequestLedger | None = None,
        units: int = 4,
    ) -> Reservation:
        identity = identity or request()
        scope = BudgetScope(
            authorization=self.scope.authorization, budget_id=identity.budget_id
        )
        return (ledger or self.ledger()).reserve(
            scope, identity, Money(units=units), operation(identity)
        )

    def proof(
        self,
        identity: RequestIdentity,
        outcome: str = "succeeded",
        units: int = 2,
        supersedes: str | None = None,
    ) -> OutcomeProof:
        fact = {
            "request": identity.model_dump(mode="json"),
            "outcome": outcome,
            "charge": None if outcome == "uncertain" else units,
        }
        fields: dict[str, object] = {
            "request": identity,
            "outcome": outcome,
            "evidence": (put(self.store, fact),),
        }
        if outcome != "uncertain":
            fields["charge"] = Money(units=units)
        if outcome in ("succeeded", "charged_failure"):
            fields.update(
                response_ref=put(
                    self.store, {"response": "unit", "request": identity.request_id}
                ),
                provider_request_id="provider-" + identity.request_id,
            )
        if outcome == "released_not_dispatched":
            fields["writer_termination_ref"] = put(
                self.store,
                {"ended": True, "owner": identity.owner.model_dump(mode="json")},
            )
        if supersedes is not None:
            fields["supersedes"] = supersedes
        return OutcomeProof.model_validate(fields)


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    (tmp_path / "evidence").mkdir()
    (tmp_path / "ledger").mkdir()
    store = FileEvidenceStore(tmp_path / "evidence")
    auth = BudgetAuthorization(
        authorization_id="authorization",
        authorization_ref=put(store, {"unit_authorization": True}),
        ceiling=Money(units=10),
        budgets=(
            BudgetLimit(budget_id="a", ceiling=Money(units=7)),
            BudgetLimit(budget_id="b", ceiling=Money(units=7)),
        ),
    )
    return Harness(
        tmp_path,
        store,
        BudgetScope(authorization=auth, budget_id="a"),
        UnitAuthority(store),
    )


def test_reserve_dispatch_settle_reopen_and_original_receipt(harness: Harness) -> None:
    identity = request()
    ledger = harness.ledger()
    reservation = harness.reserve(identity, ledger=ledger)
    saved = harness.path.read_bytes()
    assert (
        harness.reserve(identity) == reservation and harness.path.read_bytes() == saved
    )
    permit = ledger.mark_dispatching(reservation, 0, operation(identity))
    assert permit.request == identity and permit.request_revision == 1
    with pytest.raises(DispatchAlreadyCommitted):
        harness.ledger().mark_dispatching(reservation, 0, operation(identity))
    first = harness.proof(identity)
    receipt = ledger.settle(identity, first, 1, operation(identity))
    assert receipt.record.held.units == 0 and receipt.record.charged.units == 2
    correction = harness.proof(
        identity, "charge_corrected", units=3, supersedes=first.digest
    )
    ledger.settle(identity, correction, 2, operation(identity))
    saved = harness.path.read_bytes()
    assert harness.ledger().settle(identity, first, 0, operation(identity)) == receipt
    assert (
        harness.path.read_bytes() == saved
        and harness.ledger().read(identity, operation(identity)).charged.units == 3
    )


def test_unknown_keeps_shared_reservation_and_overage_blocks_sends(
    harness: Harness,
) -> None:
    identity = request()
    ledger = harness.ledger()
    reservation = harness.reserve(identity, units=7)
    second = request("second", budget="b", run="other")
    second_res = harness.reserve(second, units=3)
    ledger.mark_dispatching(reservation, 0, operation(identity))
    ledger.settle(
        identity, harness.proof(identity, "uncertain"), 1, operation(identity)
    )
    with pytest.raises(BudgetExceeded):
        harness.reserve(request("other", budget="b", run="other"), units=4)
    with pytest.raises(BudgetReconciliationRequired):
        ledger.mark_dispatching(second_res, 0, operation(second))
    ledger.settle(identity, harness.proof(identity, units=11), 2, operation(identity))
    assert ledger.read(identity, operation(identity)).charged.units == 11
    with pytest.raises(BudgetExceeded):
        ledger.mark_dispatching(second_res, 0, operation(second))


def test_release_needs_cleanup_proof_and_no_dispatch(harness: Harness) -> None:
    identity = request()
    ledger = harness.ledger()
    harness.reserve(identity)
    proof = harness.proof(identity, "released_not_dispatched", units=0)
    with pytest.raises(OwnershipConflict):
        ledger.settle(identity, proof, 0, operation(identity))
    receipt = ledger.settle(identity, proof, 0, operation(identity, cleanup=True))
    assert (
        receipt.record.state == "released_not_dispatched"
        and receipt.record.held.units == 0
    )


@pytest.mark.parametrize(
    "change", ["authorization", "capacity", "owner", "logical_alias"]
)
def test_frozen_scope_and_logical_identity_reject_rebinding(
    harness: Harness, change: str
) -> None:
    identity = request()
    harness.reserve(identity)
    before = harness.path.read_bytes()
    with pytest.raises(OwnershipConflict):
        if change == "authorization":
            altered = harness.scope.authorization.model_copy(
                update={"ceiling": Money(units=11)}
            )
            harness.ledger(authorization=altered).read(identity, operation(identity))
        elif change == "capacity":
            harness.ledger(limits=capacity(max_entries=101)).read(
                identity, operation(identity)
            )
        elif change == "owner":
            harness.ledger().read(identity, operation(request(run="elsewhere")))
        else:
            harness.reserve(identity.model_copy(update={"request_id": "alias"}))
    assert harness.path.read_bytes() == before


@pytest.mark.parametrize("stage", ["reserve", "dispatch", "settle"])
def test_authority_denial_no_budget_mutation(harness: Harness, stage: str) -> None:
    identity = request()
    ledger = harness.ledger()
    if stage != "reserve":
        res = harness.reserve(identity)
    if stage == "settle":
        ledger.mark_dispatching(res, 0, operation(identity))
    before = harness.path.read_bytes() if harness.path.exists() else None
    harness.authority.denied = True
    with pytest.raises(OwnershipConflict):
        if stage == "reserve":
            harness.reserve(identity)
        elif stage == "dispatch":
            ledger.mark_dispatching(res, 0, operation(identity))
        else:
            ledger.settle(identity, harness.proof(identity), 1, operation(identity))
    assert (harness.path.read_bytes() if harness.path.exists() else None) == before


def test_missing_or_wrong_proof_is_not_settled(harness: Harness) -> None:
    identity = request()
    ledger = harness.ledger()
    res = harness.reserve(identity)
    ledger.mark_dispatching(res, 0, operation(identity))
    before = harness.path.read_bytes()
    proof = harness.proof(identity).model_copy(
        update={"evidence": (harness.scope.authorization.authorization_ref,)}
    )
    with pytest.raises(OwnershipConflict):
        ledger.settle(identity, proof, 1, operation(identity))
    proof = harness.proof(identity)
    ref = proof.response_ref
    assert ref is not None
    (harness.root / "evidence" / "blobs" / ref.sha256).unlink()
    with pytest.raises(EvidenceNotFound):
        ledger.settle(identity, proof, 1, operation(identity))
    assert harness.path.read_bytes() == before


@pytest.mark.parametrize("revision", [None, True, -1, 0.0, "0", []])
def test_invalid_revision_rejected(harness: Harness, revision: object) -> None:
    identity = request()
    res = harness.reserve(identity)
    before = harness.path.read_bytes()
    with pytest.raises(ValueError):
        harness.ledger().mark_dispatching(res, cast(int, revision), operation(identity))
    assert harness.path.read_bytes() == before


def test_stale_revision_and_empty_read_do_not_create_state(harness: Harness) -> None:
    identity = request()
    ledger = harness.ledger()
    with pytest.raises(EvidenceNotFound):
        ledger.read(identity, operation(identity))
    assert not harness.path.exists()
    res = harness.reserve(identity)
    with pytest.raises(RevisionConflict):
        ledger.mark_dispatching(res, 1, operation(identity))


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{",
        b"{}",
        b'{"schema_version":"budget-journal-snapshot/0"}',
        b"x" * (1024 * 1024 + 1),
    ],
)
def test_corrupt_journal_never_replaced(harness: Harness, raw: bytes) -> None:
    harness.reserve()
    harness.path.write_bytes(raw)
    with pytest.raises(EvidenceIntegrityError):
        harness.reserve()
    assert harness.path.read_bytes() == raw


@pytest.mark.parametrize(
    "kind", ["snapshot_link", "snapshot_fifo", "lock_link", "lock_fifo"]
)
def test_unsafe_snapshot_and_lock_rejected(harness: Harness, kind: str) -> None:
    destination = (
        Path(str(harness.path) + ".lock") if kind.startswith("lock") else harness.path
    )
    other = harness.root / "foreign"
    other.write_bytes(b"untouched")
    if kind.endswith("link"):
        destination.symlink_to(other)
    else:
        os.mkfifo(destination)
    with pytest.raises(EvidenceIntegrityError):
        harness.reserve()
    assert other.read_bytes() == b"untouched"


def test_lock_wait_deadline(harness: Harness) -> None:
    identity = request()
    lock = Path(str(harness.path) + ".lock")
    with lock.open("wb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        with pytest.raises(OperationStopped):
            harness.ledger().reserve(
                harness.scope,
                identity,
                Money(units=4),
                operation(identity, seconds=0.1),
            )
    assert not harness.path.exists()


def test_deleted_snapshot_cannot_recreate_budget(harness: Harness) -> None:
    identity = request()
    ledger = harness.ledger()
    res = harness.reserve(identity)
    ledger.mark_dispatching(res, 0, operation(identity))
    harness.path.unlink()
    with pytest.raises(EvidenceIntegrityError):
        harness.reserve(request("another", budget="b"))
    assert not harness.path.exists()


def test_byte_exhaustion_still_allows_bounded_final_charge(harness: Harness) -> None:
    identity = request()
    limits = capacity(
        max_requests=1, max_entries=100, max_entry_bytes=4096, max_bytes=20000
    )
    ledger = harness.ledger(limits=limits)
    res = harness.reserve(identity, ledger=ledger)
    ledger.mark_dispatching(res, 0, operation(identity))
    revision = 1
    for index in range(50):
        proof = harness.proof(identity, "uncertain").model_copy(
            update={"provider_request_id": "fact-" + str(index)}
        )
        try:
            ledger.settle(identity, proof, revision, operation(identity))
        except SettlementPending as error:
            assert isinstance(error.__cause__, JournalCapacityExceeded)
            break
        revision += 1
    else:
        pytest.fail("byte limit did not stop repeated unknown observations")
    assert revision < 99
    receipt = ledger.settle(
        identity, harness.proof(identity, units=12), revision, operation(identity)
    )
    assert receipt.record.charged.units == 12
    assert harness.path.stat().st_size <= limits.max_bytes


def test_pending_charge_blocks_other_workers_until_reconciled(harness: Harness) -> None:
    limits = capacity(max_requests=2, max_entries=8)
    ledger = harness.ledger(limits=limits)
    first = request()
    second = request("second", budget="b", run="other")
    first_res = harness.reserve(first, ledger=ledger)
    second_res = harness.reserve(second, ledger=ledger, units=2)
    ledger.mark_dispatching(first_res, 0, operation(first))
    ledger.settle(first, harness.proof(first, "uncertain"), 1, operation(first))
    paid = harness.proof(first)
    ledger.settle(first, paid, 2, operation(first))
    correction = harness.proof(
        first, "charge_corrected", units=3, supersedes=paid.digest
    )
    with pytest.raises(SettlementPending):
        ledger.settle(first, correction, 3, operation(first))
    other = harness.ledger(limits=limits)
    with pytest.raises(BudgetReconciliationRequired):
        other.mark_dispatching(second_res, 0, operation(second))
    with pytest.raises(BudgetReconciliationRequired):
        harness.reserve(
            request("third", budget="b", run="third"), ledger=other, units=1
        )
    other.settle(
        second,
        harness.proof(second, "released_not_dispatched", units=0),
        0,
        operation(second, cleanup=True),
    )
    assert list((harness.root / "ledger").glob("*.pending-*"))
    receipt = other.settle(first, correction, 3, operation(first))
    assert receipt.record.charged.units == 3
    assert not list((harness.root / "ledger").glob("*.pending-*"))


def test_committed_receipt_replay_only_resolves_failed_fence_cleanup(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = request()
    ledger = harness.ledger()
    res = harness.reserve(identity)
    ledger.mark_dispatching(res, 0, operation(identity))
    proof = harness.proof(identity)
    unlink = os.unlink

    def fail_clear(path: str, *, dir_fd: int) -> None:
        if path.endswith(".pending-" + proof.digest):
            raise OSError("pending clear failed")
        unlink(path, dir_fd=dir_fd)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "unlink", fail_clear)
        with pytest.raises(SettlementPending):
            ledger.settle(identity, proof, 1, operation(identity))
    committed = harness.path.read_bytes()
    assert list((harness.root / "ledger").glob("*.pending-*"))
    assert (
        ledger.settle(identity, proof, 1, operation(identity)).record.state
        == "succeeded"
    )
    assert harness.path.read_bytes() == committed
    assert not list((harness.root / "ledger").glob("*.pending-*"))


def test_extra_correction_at_full_capacity_retains_exact_proof(
    harness: Harness,
) -> None:
    identity = request()
    ledger = harness.ledger(limits=capacity(max_requests=1, max_entries=4))
    res = harness.reserve(identity, ledger=ledger)
    ledger.mark_dispatching(res, 0, operation(identity))
    ledger.settle(
        identity, harness.proof(identity, "uncertain"), 1, operation(identity)
    )
    original = harness.proof(identity)
    ledger.settle(identity, original, 2, operation(identity))
    before = harness.path.read_bytes()
    correction = harness.proof(
        identity, "charge_corrected", units=50, supersedes=original.digest
    )
    with pytest.raises(SettlementPending) as caught:
        ledger.settle(identity, correction, 3, operation(identity))
    assert isinstance(caught.value.__cause__, JournalCapacityExceeded)
    assert (
        OutcomeProof.model_validate_json(harness.store.read(caught.value.proof_ref))
        == correction
    )
    assert harness.path.read_bytes() == before


def test_lost_dispatch_ack_never_issues_replacement_permit(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = request()
    ledger = harness.ledger()
    res = harness.reserve(identity)
    real = os.fsync

    def fail_directory(fd: int) -> None:
        real(fd)
        if os.readlink(f"/proc/self/fd/{fd}") == str(harness.root / "ledger"):
            raise OSError("lost dispatch ack")

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "fsync", fail_directory)
        with pytest.raises(OSError):
            ledger.mark_dispatching(res, 0, operation(identity))
    assert harness.ledger().read(identity, operation(identity)).state == "dispatching"
    with pytest.raises(DispatchAlreadyCommitted):
        harness.ledger().mark_dispatching(res, 0, operation(identity))


@pytest.mark.parametrize("published", [False, True])
def test_settlement_commit_failure_retains_proof_and_reconciles(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, published: bool
) -> None:
    identity = request()
    ledger = harness.ledger()
    res = harness.reserve(identity)
    ledger.mark_dispatching(res, 0, operation(identity))
    proof = harness.proof(identity)
    before = harness.path.read_bytes()
    real = os.fsync
    real_replace = os.replace
    replaced = False

    def track_replace(
        source: str, destination: str, *, src_dir_fd: int, dst_dir_fd: int
    ) -> None:
        nonlocal replaced
        real_replace(source, destination, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
        if destination == harness.path.name:
            replaced = True

    def fail_sync(fd: int) -> None:
        real(fd)
        path = os.readlink(f"/proc/self/fd/{fd}")
        if (published and replaced and path == str(harness.root / "ledger")) or (
            not published and ".pending-snapshot-" in path
        ):
            raise OSError("ledger sync failed")

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", track_replace)
        scoped.setattr(os, "fsync", fail_sync)
        with pytest.raises(SettlementPending) as caught:
            ledger.settle(identity, proof, 1, operation(identity))
    saved = caught.value.proof_ref
    assert (
        saved.sha256 == proof.digest
        and OutcomeProof.model_validate_json(harness.store.read(saved)) == proof
    )
    assert isinstance(caught.value.__cause__, OSError)
    assert (harness.path.read_bytes() != before) == published
    receipt = harness.ledger().settle(identity, proof, 1, operation(identity))
    assert receipt.record.state == "succeeded" and len(receipt.record.events) == 3


def test_near_capacity_preserves_final_settlement(harness: Harness) -> None:
    identity = request()
    limits = capacity(max_requests=1, max_entries=4)
    ledger = harness.ledger(limits=limits)
    res = harness.reserve(identity, ledger=ledger)
    ledger.mark_dispatching(res, 0, operation(identity))
    ledger.settle(
        identity, harness.proof(identity, "uncertain"), 1, operation(identity)
    )
    another = harness.proof(identity, "uncertain").model_copy(
        update={"provider_request_id": "new-fact"}
    )
    with pytest.raises(SettlementPending) as caught:
        ledger.settle(identity, another, 2, operation(identity))
    assert isinstance(caught.value.__cause__, JournalCapacityExceeded)
    receipt = ledger.settle(
        identity, harness.proof(identity, units=20), 2, operation(identity)
    )
    assert receipt.record.charged.units == 20 and receipt.record.held.units == 0
    snap = BudgetJournalSnapshot.model_validate_json(harness.path.read_bytes())
    snap.check_capacity()
    assert len(snap.history.entries) == 4


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_requests", 0),
        ("max_requests", True),
        ("max_requests", 2501),
        ("max_entries", 3),
        ("max_entries", 10001),
        ("max_bytes", 0),
        ("max_bytes", 8 * 1024 * 1024 + 1),
        ("max_entry_bytes", None),
        ("max_entry_bytes", "100"),
    ],
)
def test_invalid_capacity(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        BudgetJournalCapacity.model_validate({**capacity().model_dump(), field: value})


def test_capacity_preflight_and_per_entry_no_budget_mutation(harness: Harness) -> None:
    with pytest.raises(JournalCapacityExceeded):
        harness.ledger(
            limits=capacity(
                max_requests=1, max_entries=4, max_entry_bytes=1, max_bytes=4 * 3
            )
        )
    ledger = harness.ledger(limits=capacity(max_entry_bytes=100))
    with pytest.raises(JournalCapacityExceeded):
        harness.reserve(ledger=ledger)
    assert not harness.path.exists()


def _race(root: str, auth_json: str, index: int, dispatch: bool) -> None:
    path = Path(root)
    store = FileEvidenceStore(path / "evidence")
    auth = BudgetAuthorization.model_validate_json(auth_json)
    ledger = FileRequestLedger(
        path / "ledger",
        auth,
        capacity(),
        OperationGuards(SystemClock(), NoCancel()),
        store,
        UnitAuthority(store),
        dispatch_policy=BudgetDispatchPolicy(max_unsettled_dispatches=1),
    )
    identity = (
        request()
        if dispatch
        else request(
            "race-" + str(index),
            budget="a" if index % 2 == 0 else "b",
            run="run-" + str(index),
        )
    )
    scope = BudgetScope(authorization=auth, budget_id=identity.budget_id)
    result: str
    try:
        if dispatch:
            res = ledger.read(identity, operation(identity)).reservation
            result = ledger.mark_dispatching(res, 0, operation(identity)).schema_version
        else:
            ledger.reserve(scope, identity, Money(units=7), operation(identity))
            result = "reserved"
    except (BudgetExceeded, DispatchAlreadyCommitted) as error:
        result = type(error).__name__
    (path / ("result-" + str(index))).write_text(result)


def join(process: BaseProcess) -> None:
    process.join(20)
    if process.is_alive():
        process.kill()
        process.join(5)
        pytest.fail("worker exceeded bound")
    assert process.exitcode == 0


@pytest.mark.parametrize("dispatch", [False, True])
def test_separate_processes_share_total_budget_and_single_permit(
    harness: Harness, dispatch: bool
) -> None:
    if dispatch:
        harness.reserve()
    context = multiprocessing.get_context("spawn")
    workers = [
        context.Process(
            target=_race,
            args=(
                str(harness.root),
                harness.scope.authorization.model_dump_json(),
                i,
                dispatch,
            ),
        )
        for i in range(4)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        join(worker)
    results = [(harness.root / ("result-" + str(i))).read_text() for i in range(4)]
    assert results.count("dispatch-permit/1" if dispatch else "reserved") == 1
    assert (
        results.count("DispatchAlreadyCommitted" if dispatch else "BudgetExceeded") == 3
    )
    snap = BudgetJournalSnapshot.model_validate_json(harness.path.read_bytes())
    snap.check_capacity()
    assert snap.history.held.units == (4 if dispatch else 7)
