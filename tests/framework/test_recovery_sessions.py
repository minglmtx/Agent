"""Real persistent sessions; authority fixtures do not stand in for Slurm.

The crash-chain test records supervisor-observed exits for both the original
writer and an interrupted recovery writer, using a third process to finish.
"""

import json
import multiprocessing
from multiprocessing.process import BaseProcess
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from test_recovery import (
    FileBackend,
    Harness,
    harness as harness,
    operation,
    load,
    record_exit,
    put,
    NoCancel,
    _crash_after_effect,
)
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.recovery_sessions import FileRecoverySessions
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    ResourceOwner,
)
from lab_generate_skill.domain.recovery import (
    RecoveryIntent,
    RecoveryReceipt,
    RecoveryResult,
    WriterTerminationReceipt,
)
from lab_generate_skill.domain.recovery_sessions import (
    RecoverySessionAttempt,
    RecoverySessionRecord,
)
from lab_generate_skill.ports.recovery import RecoverySession
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.runtime.recovery import GuardedRecoveryExecutor


class Authority:
    def __init__(self, h: Harness) -> None:
        self.h = h
        self.ended: dict[ResourceOwner, WriterTerminationReceipt] = {}
        self.calls = 0

    def confirm_ended(
        self, writer: ResourceOwner, op: OperationContext
    ) -> WriterTerminationReceipt:
        self.calls += 1
        if writer not in self.ended:
            raise OwnershipConflict("Prior recovery writer live or unknown")
        return self.ended[writer]

    def allow_fixture(self, writer: ResourceOwner) -> None:
        proof = put(self.h.store, b"unit fixture only", "fixture-exit/1")
        self.ended[writer] = WriterTerminationReceipt(
            owner=writer,
            writer_instance_id=writer.worker_id,
            authority_id="fixture",
            authority_version="1",
            observed_at=datetime.now(timezone.utc),
            descendants_terminated=True,
            evidence=(proof,),
        )


def writer(h: Harness, suffix: str = "1") -> ResourceOwner:
    return ResourceOwner(
        run_id=h.token.owner.run_id,
        owner_id="recovery",
        job_id="recovery-job",
        worker_id="worker-" + suffix,
    )


def sessions(h: Harness, authority: Authority | None = None) -> FileRecoverySessions:
    root = h.root / "sessions"
    root.mkdir(exist_ok=True)
    return FileRecoverySessions(
        root,
        OperationGuards(SystemClock(), NoCancel()),
        h.store,
        authority or Authority(h),
    )


def intent(h: Harness, who: ResourceOwner, op: OperationContext) -> RecoveryIntent:
    return RecoveryIntent(
        allocation=h.token,
        binding=h.backend.binding,
        recovery_writer=who,
        operation_id=op.operation_id,
        termination=h.termination,
    )


def path(h: Harness) -> Path:
    return next((h.root / "sessions").glob("*.recovery.json"))


def test_empty_read_and_local_begin_replay_preserve_single_intent(
    harness: Harness,
) -> None:
    store = sessions(harness)
    who, op = writer(harness), operation(harness.token, "begin")
    item = intent(harness, who, op)
    with store.hold(harness.token, who, op) as session:
        assert session.read() is None
        assert not list((harness.root / "sessions").glob("*.recovery.json"))
        session.begin(item)
        raw = path(harness).read_bytes()
        session.begin(item)
        assert path(harness).read_bytes() == raw and session.read() is None
    assert len(RecoverySessionRecord.model_validate_json(raw).attempts) == 1
    with pytest.raises(OwnershipConflict):
        session.checkpoint()


def test_released_lock_does_not_authorize_restart(harness: Harness) -> None:
    authority = Authority(harness)
    store = sessions(harness, authority)
    first, op = writer(harness), operation(harness.token, "first")
    with store.hold(harness.token, first, op) as session:
        session.begin(intent(harness, first, op))
    raw = path(harness).read_bytes()
    second, new = writer(harness, "2"), operation(harness.token, "second")
    with store.hold(harness.token, second, new) as session:
        assert session.read() is None
        with pytest.raises(OwnershipConflict, match="live or unknown"):
            session.begin(intent(harness, second, new))
    assert authority.calls == 1 and path(harness).read_bytes() == raw


def test_proven_restart_retains_prior_writer_and_proof(harness: Harness) -> None:
    authority = Authority(harness)
    store = sessions(harness, authority)
    first, op = writer(harness), operation(harness.token, "first")
    original = intent(harness, first, op)
    with store.hold(harness.token, first, op) as session:
        session.begin(original)
    authority.allow_fixture(first)
    second, new = writer(harness, "2"), operation(harness.token, "second")
    with store.hold(harness.token, second, new) as session:
        session.begin(intent(harness, second, new))
    record = RecoverySessionRecord.model_validate_json(path(harness).read_bytes())
    assert len(record.attempts) == 2 and record.attempts[0].intent == original
    assert record.attempts[1].predecessor_termination == authority.ended[first]


def test_atomic_receipt_replay_cannot_begin_again(harness: Harness) -> None:
    receipt = harness.restore()
    store = sessions(harness)
    who = receipt.intent.recovery_writer
    op = operation(harness.token, receipt.intent.operation_id)
    with store.hold(harness.token, who, op) as session:
        with pytest.raises(OwnershipConflict):
            session.commit(receipt)
        session.begin(receipt.intent)
        session.commit(receipt)
        raw = path(harness).read_bytes()
        session.commit(receipt)
        assert session.read() == receipt and path(harness).read_bytes() == raw
        with pytest.raises(OwnershipConflict):
            session.begin(receipt.intent)
    with store.hold(
        harness.token, writer(harness, "later"), operation(harness.token, "read-only")
    ) as session:
        assert session.read() == receipt


@pytest.mark.parametrize("fault", ["replace", "file_fsync", "write"])
def test_precommit_fault_has_no_partial_snapshot(harness: Harness, fault: str) -> None:
    store = sessions(harness)
    who, op = writer(harness), operation(harness.token, "fault")
    target = {"replace": "replace", "file_fsync": "fsync", "write": "write"}[fault]
    with store.hold(harness.token, who, op) as session:
        with (
            patch.object(os, target, side_effect=OSError("write fault")),
            pytest.raises(OSError),
        ):
            session.begin(intent(harness, who, op))
        assert not list((harness.root / "sessions").glob("*.recovery.json"))
        assert not list((harness.root / "sessions").glob(".pending-*"))


def test_lost_intent_ack_same_held_session_can_reconcile(harness: Harness) -> None:
    store = sessions(harness)
    who, op = writer(harness), operation(harness.token, "fault")
    item = intent(harness, who, op)
    with store.hold(harness.token, who, op) as session:
        with (
            patch.object(os, "fsync", side_effect=[None, OSError("ack lost")]),
            pytest.raises(OSError),
        ):
            session.begin(item)
        raw = path(harness).read_bytes()
        session.begin(item)
        assert path(harness).read_bytes() == raw


def test_write_and_cleanup_errors_remain_separate(harness: Harness) -> None:
    store = sessions(harness)
    who, op = writer(harness), operation(harness.token, "fault")
    with store.hold(harness.token, who, op) as session:
        with (
            patch.object(os, "replace", side_effect=OSError("publish")),
            patch.object(os, "unlink", side_effect=OSError("cleanup")),
            pytest.raises(ExceptionGroup) as caught,
        ):
            session.begin(intent(harness, who, op))
        assert [str(e) for e in caught.value.exceptions] == ["publish", "cleanup"]
        assert not list((harness.root / "sessions").glob("*.recovery.json"))


def test_body_and_session_close_failures_are_retained(harness: Harness) -> None:
    store = sessions(harness)
    who, op = writer(harness), operation(harness.token, "fault")
    real_close = os.close

    def fail(fd: int) -> None:
        real_close(fd)
        raise OSError("close")

    with (
        patch.object(os, "close", side_effect=fail),
        pytest.raises(ExceptionGroup) as caught,
    ):
        with store.hold(harness.token, who, op):
            raise RuntimeError("backend")
    assert [str(e) for e in caught.value.exceptions] == ["backend", "close", "close"]


@pytest.mark.parametrize(
    "fault", ["empty", "truncated", "wrong_schema", "oversize", "symlink", "fifo"]
)
def test_corrupt_or_unsafe_snapshot_never_repaired(
    harness: Harness, fault: str
) -> None:
    store = sessions(harness)
    who, op = writer(harness), operation(harness.token, "setup")
    with store.hold(harness.token, who, op) as session:
        session.begin(intent(harness, who, op))
    name = path(harness)
    if fault in ("symlink", "fifo"):
        name.unlink()
        if fault == "symlink":
            name.symlink_to(harness.root / "token.json")
        else:
            os.mkfifo(name)
    elif fault == "oversize":
        name.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    elif fault == "wrong_schema":
        name.write_text(
            name.read_text().replace(
                "recovery-session-record/1", "recovery-session-record/99"
            )
        )
    else:
        name.write_text("" if fault == "empty" else "{")
    with store.hold(
        harness.token, writer(harness, "read"), operation(harness.token, "read")
    ) as session:
        with pytest.raises(EvidenceIntegrityError):
            session.read()


def test_checkpoint_rejects_replaced_lock_and_other_thread(harness: Harness) -> None:
    store = sessions(harness)
    who, op = writer(harness), operation(harness.token, "scope")
    with store.hold(harness.token, who, op) as session:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(OwnershipConflict):
                pool.submit(session.checkpoint).result()
        lock = next((harness.root / "sessions").glob("*.lock"))
        lock.unlink()
        lock.write_bytes(b"")
        with pytest.raises(OwnershipConflict):
            session.checkpoint()


def test_capacity_reserves_space_for_current_receipt(harness: Harness) -> None:
    receipt = harness.restore()
    store = sessions(harness)
    item = RecoverySessionAttempt(intent=receipt.intent)
    record = RecoverySessionRecord(allocation=harness.token, attempts=(item,))
    exact = len(record.model_dump_json().encode()) + 4096
    op = operation(harness.token, receipt.intent.operation_id)
    with patch.object(FileRecoverySessions, "_MAX_BYTES", exact):
        with store.hold(harness.token, receipt.intent.recovery_writer, op) as session:
            session.begin(receipt.intent)
            session.commit(receipt)
            assert session.read() == receipt and path(harness).stat().st_size <= exact


@pytest.mark.parametrize("attempts", [(), None, [], "", ({"bad": 1},)])
def test_invalid_empty_lineage_rejected(harness: Harness, attempts: object) -> None:
    with pytest.raises(ValidationError):
        RecoverySessionRecord.model_validate(
            {"allocation": harness.token, "attempts": attempts}
        )


class ExitFileAuthority:
    def __init__(self, h: Harness) -> None:
        self.h = h

    def confirm_ended(
        self, writer: ResourceOwner, op: OperationContext
    ) -> WriterTerminationReceipt:
        data = json.loads((self.h.root / "recovery-exit.json").read_text())
        if data != {
            "owner": writer.model_dump(mode="json"),
            "exitcode": 29,
            "children": [],
        }:
            raise OwnershipConflict("Supervisor has not confirmed this writer")
        proof = put(self.h.store, json.dumps(data).encode(), "fixture-recovery-exit/1")
        return WriterTerminationReceipt(
            owner=writer,
            writer_instance_id=writer.worker_id,
            authority_id="test-supervisor",
            authority_version="1",
            observed_at=datetime.now(timezone.utc),
            descendants_terminated=True,
            evidence=(proof,),
        )


class PersistentFixtureBackend(FileBackend):
    def verify_intent(self, token: AllocationToken, op: OperationContext) -> None:
        name = next((self.root / "sessions").glob("*.recovery.json"))
        record = RecoverySessionRecord.model_validate_json(name.read_bytes())
        assert record.allocation == token
        assert record.attempts[-1].intent.operation_id == op.operation_id
        assert record.attempts[-1].receipt_ref is None


def _recovery_process(root: str, crash: bool) -> None:
    h = load(Path(root))
    h.backend = PersistentFixtureBackend(h.root, h.store)
    directory = h.root / "sessions"
    directory.mkdir(exist_ok=True)
    controls = OperationGuards(SystemClock(), NoCancel())
    who = ResourceOwner(
        run_id=h.token.owner.run_id,
        owner_id="recovery",
        job_id="recovery-job",
        worker_id=str(os.getpid()),
    )
    store = FileRecoverySessions(directory, controls, h.store, ExitFileAuthority(h))
    executor = GuardedRecoveryExecutor(
        who, h.journal, h.store, controls, h.verifier, store, h.backend
    )
    if crash:

        def interrupted(
            token: AllocationToken,
            plan: object,
            control: RecoverySession,
            op: OperationContext,
        ) -> RecoveryResult:
            control.checkpoint()
            h.backend.verify_intent(token, op)
            (h.root / "state").write_text("recovery partially modified state")
            os._exit(29)

        with patch.object(h.backend, "restore", side_effect=interrupted):
            executor.restore(
                h.token, h.plan, h.termination, operation(h.token, "first-recovery")
            )
    else:
        receipt = executor.restore(
            h.token, h.plan, h.termination, operation(h.token, "next-recovery")
        )
        assert receipt.status == "restored"


def join_bounded(process: BaseProcess, expected: int) -> None:
    process.join(20)
    if process.is_alive():
        process.terminate()
        process.join(5)
        pytest.fail("Process exceeded recovery test deadline")
    assert process.exitcode == expected


def test_original_and_recovery_writer_crashes_recover_from_persistent_history(
    tmp_path: Path,
) -> None:
    ctx = multiprocessing.get_context("spawn")
    original = ctx.Process(target=_crash_after_effect, args=(str(tmp_path),))
    original.start()
    join_bounded(original, 23)
    assert original.pid is not None
    record_exit(tmp_path, original.pid)
    recovery = ctx.Process(target=_recovery_process, args=(str(tmp_path), True))
    recovery.start()
    join_bounded(recovery, 29)
    snapshot_path = next((tmp_path / "sessions").glob("*.recovery.json"))
    before = RecoverySessionRecord.model_validate_json(snapshot_path.read_bytes())
    prior = before.attempts[-1].intent.recovery_writer
    assert (
        prior.worker_id == str(recovery.pid) and before.attempts[-1].receipt_ref is None
    )
    assert (tmp_path / "state").read_text() == "recovery partially modified state"
    (tmp_path / "recovery-exit.json").write_text(
        json.dumps(
            {"owner": prior.model_dump(mode="json"), "exitcode": 29, "children": []}
        )
    )
    successor = ctx.Process(target=_recovery_process, args=(str(tmp_path), False))
    successor.start()
    join_bounded(successor, 0)
    after = RecoverySessionRecord.model_validate_json(snapshot_path.read_bytes())
    assert len(after.attempts) == 2 and after.attempts[0] == before.attempts[0]
    assert after.attempts[1].predecessor_termination is not None
    assert after.attempts[1].predecessor_termination.owner == prior
    assert after.attempts[1].receipt_ref is not None
    assert after.allocation.owner.worker_id == str(original.pid)
    assert (tmp_path / "state").read_bytes() == b"baseline"


def test_lock_contention_obeys_deadline(harness: Harness) -> None:
    store = sessions(harness)
    who, op = writer(harness), operation(harness.token, "holder")
    impatient = operation(harness.token, "waiter")
    impatient = OperationContext.model_validate(
        {
            **impatient.model_dump(),
            "deadline": datetime.now(timezone.utc) + timedelta(seconds=0.1),
        }
    )
    with store.hold(harness.token, who, op) as first:
        with pytest.raises(OperationStopped):
            with store.hold(harness.token, writer(harness, "waiting"), impatient):
                pytest.fail("Concurrent recovery unexpectedly acquired lock")
        first.checkpoint()
    assert not list((harness.root / "sessions").glob("*.recovery.json"))


def test_receipt_directory_sync_lost_ack_does_not_duplicate_commit(
    harness: Harness,
) -> None:
    receipt = harness.restore()
    store = sessions(harness)
    op = operation(harness.token, receipt.intent.operation_id)
    real_sync = os.fsync

    def fail_directory(fd: int) -> None:
        real_sync(fd)
        if os.readlink(f"/proc/self/fd/{fd}") == str(harness.root / "sessions"):
            raise OSError("receipt ack lost")

    with store.hold(harness.token, receipt.intent.recovery_writer, op) as session:
        session.begin(receipt.intent)
        with (
            patch.object(os, "fsync", side_effect=fail_directory),
            pytest.raises(OSError, match="receipt ack"),
        ):
            session.commit(receipt)
        committed = path(harness).read_bytes()
        session.commit(receipt)
        assert session.read() == receipt and path(harness).read_bytes() == committed


@pytest.mark.parametrize("fault", ["wrong_owner", "missing_proof", "unconfirmed"])
def test_bad_predecessor_authority_cannot_append(harness: Harness, fault: str) -> None:
    authority = Authority(harness)
    store = sessions(harness, authority)
    first, op = writer(harness), operation(harness.token, "first")
    with store.hold(harness.token, first, op) as session:
        session.begin(intent(harness, first, op))
    authority.allow_fixture(first)
    proof = authority.ended[first]
    if fault == "wrong_owner":
        authority.ended[first] = WriterTerminationReceipt.model_validate(
            {**proof.model_dump(), "owner": writer(harness, "wrong")}
        )
    elif fault == "unconfirmed":
        authority.ended[first] = proof.model_copy(
            update={"descendants_terminated": False}
        )
    else:
        (harness.root / "evidence" / "blobs" / proof.evidence[0].sha256).unlink()
    prior = path(harness).read_bytes()
    who, new = writer(harness, "second"), operation(harness.token, "second")
    with store.hold(harness.token, who, new) as session:
        with pytest.raises((OwnershipConflict, ValidationError, EvidenceNotFound)):
            session.begin(intent(harness, who, new))
    assert path(harness).read_bytes() == prior


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate_writer",
        "duplicate_operation",
        "wrong_predecessor",
        "changed_binding",
        "terminal_prefix",
    ],
)
def test_lineage_rejects_unsafe_restart_history(harness: Harness, fault: str) -> None:
    first = writer(harness)
    a = intent(harness, first, operation(harness.token, "first"))
    b = intent(harness, writer(harness, "second"), operation(harness.token, "second"))
    proof = WriterTerminationReceipt.model_validate(
        {**harness.termination.model_dump(), "owner": first}
    )
    first_attempt = RecoverySessionAttempt(intent=a)
    if fault == "duplicate_writer":
        b = RecoveryIntent.model_validate({**b.model_dump(), "recovery_writer": first})
    elif fault == "duplicate_operation":
        b = RecoveryIntent.model_validate(
            {**b.model_dump(), "operation_id": a.operation_id}
        )
    elif fault == "wrong_predecessor":
        proof = WriterTerminationReceipt.model_validate(
            {**proof.model_dump(), "owner": writer(harness, "wrong")}
        )
    elif fault == "changed_binding":
        b = RecoveryIntent.model_validate(
            {
                **b.model_dump(),
                "binding": {**b.binding.model_dump(), "component_version": "2"},
            }
        )
    else:
        ref = put(harness.store, b"{}", "recovery-receipt/1")
        first_attempt = RecoverySessionAttempt(intent=a, receipt_ref=ref)
    with pytest.raises(ValidationError):
        RecoverySessionRecord(
            allocation=harness.token,
            attempts=(
                first_attempt,
                RecoverySessionAttempt(intent=b, predecessor_termination=proof),
            ),
        )


def test_attempt_limit_preserves_all_prior_intents(harness: Harness) -> None:
    attempts: list[RecoverySessionAttempt] = []
    for index in range(33):
        who = writer(harness, str(index))
        item = intent(harness, who, operation(harness.token, f"op-{index}"))
        prior = (
            WriterTerminationReceipt.model_validate(
                {
                    **harness.termination.model_dump(),
                    "owner": attempts[-1].intent.recovery_writer,
                }
            )
            if attempts
            else None
        )
        attempts.append(
            RecoverySessionAttempt(intent=item, predecessor_termination=prior)
        )
    valid = RecoverySessionRecord(
        allocation=harness.token, attempts=tuple(attempts[:32])
    )
    assert len(valid.attempts) == 32
    with pytest.raises(ValidationError):
        RecoverySessionRecord(allocation=harness.token, attempts=tuple(attempts))


def test_corrupt_receipt_payload_is_not_reported_as_success(harness: Harness) -> None:
    receipt = harness.restore()
    store = sessions(harness)
    op = operation(harness.token, receipt.intent.operation_id)
    with store.hold(harness.token, receipt.intent.recovery_writer, op) as session:
        session.begin(receipt.intent)
        session.commit(receipt)
    record = RecoverySessionRecord.model_validate_json(path(harness).read_bytes())
    bad = put(harness.store, b'{"wrong":"payload"}', "recovery-receipt/1")
    replacement = RecoverySessionAttempt(
        intent=record.attempts[-1].intent, receipt_ref=bad
    )
    path(harness).write_text(
        RecoverySessionRecord(
            allocation=harness.token, attempts=(replacement,)
        ).model_dump_json()
    )
    with store.hold(
        harness.token, writer(harness, "read"), operation(harness.token, "read-bad")
    ) as session:
        with pytest.raises(EvidenceIntegrityError, match="stored recovery receipt"):
            session.read()


def _compete(root: str, index: int) -> None:
    import time

    h = load(Path(root))
    store = sessions(h)
    who = writer(h, str(os.getpid()))
    op = operation(h.token, f"compete-{index}")
    try:
        with store.hold(h.token, who, op) as session:
            session.begin(intent(h, who, op))
            time.sleep(0.1)
        result = "begun"
    except OwnershipConflict:
        result = "unknown-prior"
    (h.root / f"race-{index}.txt").write_text(result)


@pytest.mark.parametrize(
    "field", ["allocation_id", "owner", "provider_version", "resource_kind"]
)
def test_same_resource_cannot_alias_a_new_recovery_history(
    harness: Harness, field: str
) -> None:
    store = sessions(harness)
    who, op = writer(harness), operation(harness.token, "first")
    with store.hold(harness.token, who, op) as session:
        session.begin(intent(harness, who, op))
    raw = path(harness).read_bytes()
    data = harness.token.model_dump()
    if field == "owner":
        data["owner"] = {**harness.token.owner.model_dump(), "run_id": "another-run"}
    else:
        data[field] = "another"
    alias = AllocationToken.model_validate(data)
    alias_writer = ResourceOwner.model_validate(
        {**writer(harness, "alias").model_dump(), "run_id": alias.owner.run_id}
    )
    with store.hold(alias, alias_writer, operation(alias, "alias-op")) as session:
        with pytest.raises(OwnershipConflict, match="another allocation"):
            session.read()
    assert path(harness).read_bytes() == raw
    assert len(list((harness.root / "sessions").glob("*.recovery.json"))) == 1


def test_different_resource_incarnations_have_independent_locks(
    harness: Harness,
) -> None:
    store = sessions(harness)
    who, op = writer(harness), operation(harness.token, "first")
    other = AllocationToken.model_validate(
        {
            **harness.token.model_dump(),
            "allocation_id": "another-allocation",
            "expected_resource_id": "another-instance",
        }
    )
    with store.hold(harness.token, who, op) as first:
        with store.hold(
            other, writer(harness, "other"), operation(other, "other-op")
        ) as second:
            assert first.read() is second.read() is None
            first.checkpoint()
            second.checkpoint()


def test_four_processes_cannot_begin_multiple_unproved_recoveries(
    harness: Harness,
) -> None:
    ctx = multiprocessing.get_context("spawn")
    workers = [
        ctx.Process(target=_compete, args=(str(harness.root), i)) for i in range(4)
    ]
    for process in workers:
        process.start()
    for process in workers:
        join_bounded(process, 0)
    outcomes = [(harness.root / f"race-{i}.txt").read_text() for i in range(4)]
    assert outcomes.count("begun") == 1 and outcomes.count("unknown-prior") == 3
    assert (
        len(
            RecoverySessionRecord.model_validate_json(
                path(harness).read_bytes()
            ).attempts
        )
        == 1
    )
