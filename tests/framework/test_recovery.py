"""Guarded recovery with real evidence/journal and explicitly limited file fixtures.

Fixture sessions/verifier are not production Slurm authority or crash takeover
adapters. A supervisor-observed child exit is persisted for the separate-process
test; the restore process receives paths only, never an original live lease.
"""

import json
import multiprocessing
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.resource_journal import FileResourceJournal
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    CancellationRef,
    CleanupFailure,
    OperationContext,
    RecoveryPlan,
    ResourceOwner,
    ResourceState,
    ResourceRecord,
)
from lab_generate_skill.domain.recovery import (
    RecoveryBinding,
    RecoveryCheck,
    RecoveryIntent,
    RecoveryObservation,
    RecoveryReceipt,
    RecoveryResult,
    WriterTerminationReceipt,
)
from lab_generate_skill.ports.recovery import RecoverySession
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.runtime.recovery import GuardedRecoveryExecutor


class NoCancel:
    def is_cancelled(self, ref: CancellationRef) -> bool:
        return False


def put(store: FileEvidenceStore, data: bytes, schema: str) -> EvidenceRef:
    return store.put(
        data,
        EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer="test-supervisor",
        ),
    )


def operation(
    token: AllocationToken, name: str, cleanup: bool = True
) -> OperationContext:
    return OperationContext(
        operation_id=name,
        run_id=token.owner.run_id,
        owner_id=token.owner.owner_id,
        attempt_id=token.attempt_id,
        allocation_id=token.allocation_id,
        recovery_ref=token.recovery_ref,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=60),
        mode="cleanup" if cleanup else "execute",
        parent_operation_id="original-prepare" if cleanup else None,
    )


class Session:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.lost_ack = False
        self.active = False

    def checkpoint(self) -> None:
        assert self.active

    def read(self) -> RecoveryReceipt | None:
        path = self.root / "receipt.json"
        return (
            RecoveryReceipt.model_validate_json(path.read_bytes())
            if path.exists()
            else None
        )

    def begin(self, intent: RecoveryIntent) -> None:
        self.checkpoint()
        (self.root / "intent.json").write_text(intent.model_dump_json())

    def commit(self, receipt: RecoveryReceipt) -> None:
        self.checkpoint()
        (self.root / "receipt.json").write_text(receipt.model_dump_json())
        if self.lost_ack:
            raise OSError("receipt acknowledgement lost")

    @contextmanager
    def hold(
        self, allocation: AllocationToken, writer: ResourceOwner, op: OperationContext
    ) -> Iterator[RecoverySession]:
        assert not self.active
        self.active = True
        try:
            yield self
        finally:
            self.active = False


class Verifier:
    def __init__(self, store: FileEvidenceStore) -> None:
        self.store = store
        self.live = False
        self.calls = 0

    def verify(
        self,
        token: AllocationToken,
        receipt: WriterTerminationReceipt,
        op: OperationContext,
    ) -> None:
        self.calls += 1
        if (
            self.live
            or receipt.authority_id != "test-supervisor"
            or receipt.authority_version != "1"
        ):
            raise OwnershipConflict("writer live or unsupported authority")
        proof = json.loads(self.store.read(receipt.evidence[0]))
        if proof != {
            "owner": token.owner.model_dump(mode="json"),
            "instance": receipt.writer_instance_id,
            "exitcode": 23,
            "children": [],
        }:
            raise OwnershipConflict("termination facts do not match writer incarnation")


class FileBackend:
    def __init__(self, root: Path, store: FileEvidenceStore) -> None:
        self.root = root
        self.store = store
        self.calls = 0
        self.fail = False
        self.wrong_coverage = False
        self.binding = RecoveryBinding(
            component_id="file.restore",
            component_version="1",
            provider_id="file.provider",
            provider_version="1",
            resource_kind="file-fixture",
        )

    def inspect(
        self, token: AllocationToken, op: OperationContext
    ) -> RecoveryObservation:
        marker = self.root / "resource-id"
        identity = (
            marker.read_text()
            if marker.exists() and (self.root / "state").exists()
            else None
        )
        proof = put(
            self.store,
            json.dumps({"observed": identity}).encode(),
            "fixture-observation/1",
        )
        return RecoveryObservation(
            allocation_id=token.allocation_id,
            actual_resource_id=identity,
            evidence=(proof,),
        )

    def restore(
        self,
        token: AllocationToken,
        plan: RecoveryPlan,
        control: RecoverySession,
        op: OperationContext,
    ) -> RecoveryResult:
        control.checkpoint()
        self.verify_intent(token, op)
        self.calls += 1
        if not self.fail:
            (self.root / "state").write_bytes(self.store.read(plan.baseline_ref))
        proof = put(self.store, (self.root / "state").read_bytes(), "fixture-state/1")
        error = (
            CleanupFailure(
                component_id="file.restore",
                reason_code="RESTORE_FAILED",
                evidence=(proof,),
            )
            if self.fail
            else None
        )
        return RecoveryResult(
            allocation_id=token.allocation_id,
            actual_resource_id=token.expected_resource_id,
            checks=(
                RecoveryCheck(
                    coverage="other" if self.wrong_coverage else "file-state",
                    status="failed" if self.fail else "restored",
                    evidence=(proof,),
                    error=error,
                ),
            ),
        )

    def verify_intent(self, token: AllocationToken, op: OperationContext) -> None:
        saved = RecoveryIntent.model_validate_json(
            (self.root / "intent.json").read_bytes()
        )
        assert saved.allocation == token and saved.operation_id == op.operation_id


@dataclass
class Harness:
    root: Path
    store: FileEvidenceStore
    journal: FileResourceJournal
    token: AllocationToken
    plan: RecoveryPlan
    termination: WriterTerminationReceipt
    session: Session
    verifier: Verifier
    backend: FileBackend
    executor: GuardedRecoveryExecutor

    def restore(self, name: str = "recover") -> RecoveryReceipt:
        return self.executor.restore(
            self.token, self.plan, self.termination, operation(self.token, name)
        )


def load(root: Path) -> Harness:
    store = FileEvidenceStore(root / "evidence")
    token = AllocationToken.model_validate_json((root / "token.json").read_bytes())
    plan = RecoveryPlan.model_validate_json(store.read(token.recovery_ref))
    termination = WriterTerminationReceipt.model_validate_json(
        (root / "termination.json").read_bytes()
    )
    controls = OperationGuards(SystemClock(), NoCancel())
    journal = FileResourceJournal(root / "journal", token.owner, controls, store)
    writer = ResourceOwner(
        run_id=token.owner.run_id,
        owner_id="recovery",
        job_id="recovery-job",
        worker_id=str(os.getpid()),
    )
    session = Session(root)
    verifier = Verifier(store)
    backend = FileBackend(root, store)
    executor = GuardedRecoveryExecutor(
        writer, journal, store, controls, verifier, session, backend
    )
    return Harness(
        root,
        store,
        journal,
        token,
        plan,
        termination,
        session,
        verifier,
        backend,
        executor,
    )


def initialize(root: Path) -> None:
    for name in ("evidence", "journal"):
        (root / name).mkdir()
    store = FileEvidenceStore(root / "evidence")
    owner = ResourceOwner(
        run_id="run",
        owner_id="original",
        job_id="original-job",
        worker_id=str(os.getpid()),
    )
    baseline = put(store, b"baseline", "fixture-state/1")
    plan = RecoveryPlan(
        recovery_id="restore",
        owner=owner,
        attempt_id="attempt",
        baseline_ref=baseline,
        restore_component_id="file.restore",
        restore_component_version="1",
        state_coverage=("file-state",),
    )
    token = AllocationToken(
        allocation_id="allocation",
        owner=owner,
        scope="attempt",
        attempt_id="attempt",
        resource_kind="file-fixture",
        expected_resource_id="original-instance",
        provider_id="file.provider",
        provider_version="1",
        recovery_ref=put(store, plan.model_dump_json().encode(), "recovery-plan/1"),
    )
    journal = FileResourceJournal(
        root / "journal", owner, OperationGuards(SystemClock(), NoCancel()), store
    )
    journal.register(token, operation(token, "register", False))
    from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent

    acquire_op = operation(token, "begin-acquire", False)
    acquire_intent = ResourceAcquisitionIntent(
        token=token, operation=acquire_op, configuration_ref=baseline
    )
    journal.begin_acquire(
        token,
        put(
            store,
            acquire_intent.model_dump_json().encode(),
            "resource-acquisition-intent/1",
        ),
        0,
        acquire_op,
    )
    (root / "token.json").write_text(token.model_dump_json())
    (root / "resource-id").write_text(token.expected_resource_id)
    (root / "state").write_text("partial mutation")


def record_exit(root: Path, pid: int) -> None:
    token = AllocationToken.model_validate_json((root / "token.json").read_bytes())
    store = FileEvidenceStore(root / "evidence")
    proof = put(
        store,
        json.dumps(
            {
                "owner": token.owner.model_dump(mode="json"),
                "instance": str(pid),
                "exitcode": 23,
                "children": [],
            }
        ).encode(),
        "fixture-process-exit/1",
    )
    receipt = WriterTerminationReceipt(
        owner=token.owner,
        writer_instance_id=str(pid),
        authority_id="test-supervisor",
        authority_version="1",
        observed_at=datetime.now(timezone.utc),
        descendants_terminated=True,
        evidence=(proof,),
    )
    (root / "termination.json").write_text(receipt.model_dump_json())


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    initialize(tmp_path)
    # Unit fixture proof only; the integration test below records an actual exit.
    record_exit(tmp_path, os.getpid())
    return load(tmp_path)


def test_restore_uses_durable_plan_and_returns_original_receipt(
    harness: Harness,
) -> None:
    receipt = harness.restore()
    assert (
        receipt.status == "restored"
        and (harness.root / "state").read_bytes() == b"baseline"
    )
    assert harness.restore("inspect-receipt") == receipt
    assert harness.backend.calls == 1
    assert (
        harness.journal.read(harness.token, operation(harness.token, "read")).state
        == "closing"
    )


@pytest.mark.parametrize(
    "fault",
    [
        "live",
        "incarnation",
        "executor",
        "provider",
        "resource",
        "absent",
        "context",
        "plan",
        "missing_proof",
    ],
)
def test_invalid_recovery_cannot_change_original_state(
    harness: Harness, fault: str
) -> None:
    if fault == "live":
        harness.verifier.live = True
    elif fault == "incarnation":
        harness.termination = WriterTerminationReceipt.model_validate(
            {**harness.termination.model_dump(), "writer_instance_id": "other"}
        )
    elif fault in ("executor", "provider"):
        field = "component_version" if fault == "executor" else "provider_version"
        harness.backend.binding = RecoveryBinding.model_validate(
            {**harness.backend.binding.model_dump(), field: "2"}
        )
    elif fault == "resource":
        (harness.root / "resource-id").write_text("replacement")
    elif fault == "absent":
        (harness.root / "resource-id").unlink()
    elif fault == "plan":
        harness.plan = RecoveryPlan.model_validate(
            {**harness.plan.model_dump(), "state_coverage": ("invented",)}
        )
    elif fault == "missing_proof":
        (
            harness.root / "evidence" / "blobs" / harness.termination.evidence[0].sha256
        ).unlink()
    op = operation(harness.token, "recover", cleanup=fault != "context")
    with pytest.raises((OwnershipConflict, ValidationError, EvidenceNotFound)):
        harness.executor.restore(harness.token, harness.plan, harness.termination, op)
    assert harness.backend.calls == 0
    assert (harness.root / "state").read_text() == "partial mutation"
    assert not (harness.root / "receipt.json").exists()


def test_failed_restore_is_quarantined_and_not_silently_reexecuted(
    harness: Harness,
) -> None:
    harness.backend.fail = True
    receipt = harness.restore()
    assert (
        receipt.status == "quarantined" and receipt.result.checks[0].error is not None
    )
    assert (harness.root / "state").read_text() == "partial mutation"
    assert harness.restore("read-failure") == receipt and harness.backend.calls == 1
    assert (
        harness.journal.read(
            harness.token, operation(harness.token, "inspect-quarantine")
        ).state
        == "quarantined"
    )


def test_wrong_result_coverage_never_commits_success(harness: Harness) -> None:
    harness.backend.wrong_coverage = True
    with pytest.raises(OwnershipConflict, match="cover exactly"):
        harness.restore()
    assert not (harness.root / "receipt.json").exists()
    assert (harness.root / "intent.json").exists()


def test_lost_receipt_ack_reads_saved_result_without_another_restore(
    harness: Harness,
) -> None:
    harness.session.lost_ack = True
    with pytest.raises(OSError, match="acknowledgement"):
        harness.restore()
    harness.session.lost_ack = False
    assert harness.restore("reconcile").status == "restored"
    assert harness.backend.calls == 1


@pytest.mark.parametrize("value", [False, 1, 0, "true", None, [], 1.0])
def test_termination_confirmation_is_exact_boolean(
    harness: Harness, value: object
) -> None:
    with pytest.raises(ValidationError):
        WriterTerminationReceipt.model_validate(
            {**harness.termination.model_dump(), "descendants_terminated": value}
        )


def _crash_after_effect(root: str) -> None:
    initialize(Path(root))
    os._exit(23)


def _recover_in_new_process(root: str) -> None:
    harness = load(Path(root))
    assert harness.restore().status == "restored"


def test_new_process_recovers_after_real_writer_exit(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    original = context.Process(target=_crash_after_effect, args=(str(tmp_path),))
    original.start()
    original.join(20)
    if original.is_alive():
        original.terminate()
        original.join(5)
        pytest.fail("Original fixture writer did not exit")
    assert original.exitcode == 23 and original.pid is not None
    assert (tmp_path / "state").read_text() == "partial mutation"
    record_exit(tmp_path, original.pid)
    recovery = context.Process(target=_recover_in_new_process, args=(str(tmp_path),))
    recovery.start()
    recovery.join(20)
    if recovery.is_alive():
        recovery.terminate()
        recovery.join(5)
        pytest.fail("Recovery fixture exceeded deadline")
    assert recovery.exitcode == 0 and recovery.pid != original.pid
    receipt = RecoveryReceipt.model_validate_json(
        (tmp_path / "receipt.json").read_bytes()
    )
    assert receipt.intent.termination.writer_instance_id == str(original.pid)
    assert receipt.intent.recovery_writer.worker_id == str(recovery.pid)
    assert (tmp_path / "state").read_bytes() == b"baseline"


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "running"},
        {"evidence": ()},
        {"evidence": None},
        {"schema_version": "writer-termination/99"},
        {"observed_at": datetime(2026, 1, 1)},
        {"writer_instance_id": ""},
        {"authority_version": None},
        {"extra": True},
    ],
)
def test_termination_rejects_empty_unknown_and_wrong_types(
    harness: Harness, changes: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        WriterTerminationReceipt.model_validate(
            {**harness.termination.model_dump(), **changes}
        )


def test_public_termination_proof_is_refused(harness: Harness) -> None:
    ref = EvidenceRef.model_validate(
        {**harness.termination.evidence[0].model_dump(), "visibility": "public"}
    )
    with pytest.raises(ValidationError):
        WriterTerminationReceipt.model_validate(
            {**harness.termination.model_dump(), "evidence": (ref,)}
        )


@pytest.mark.parametrize(
    "status,error_present,valid",
    [
        ("restored", False, True),
        ("restored", True, False),
        ("failed", False, False),
        ("failed", True, True),
        ("unconfirmed", False, False),
        ("unconfirmed", True, True),
    ],
)
def test_each_check_keeps_failure_diagnostics(
    harness: Harness, status: str, error_present: bool, valid: bool
) -> None:
    error = (
        CleanupFailure(component_id="file.restore", reason_code="UNCONFIRMED")
        if error_present
        else None
    )
    data = {
        "coverage": "file-state",
        "status": status,
        "evidence": harness.termination.evidence,
        "error": error,
    }
    if valid:
        check = RecoveryCheck.model_validate(data)
        assert RecoveryCheck.model_validate_json(check.model_dump_json()) == check
    else:
        with pytest.raises(ValidationError):
            RecoveryCheck.model_validate(data)


def test_duplicate_coverage_and_status_relabel_are_rejected(harness: Harness) -> None:
    receipt = harness.restore()
    check = receipt.result.checks[0]
    with pytest.raises(ValidationError):
        RecoveryResult.model_validate(
            {**receipt.result.model_dump(), "checks": (check, check)}
        )
    with pytest.raises(ValidationError):
        RecoveryReceipt.model_validate(
            {**receipt.model_dump(), "status": "quarantined"}
        )


def test_replayed_receipt_termination_is_also_authority_verified(
    harness: Harness,
) -> None:
    receipt = harness.restore()
    data = receipt.model_dump()
    data["intent"]["termination"]["writer_instance_id"] = "another-incarnation"
    altered = RecoveryReceipt.model_validate(data)
    (harness.root / "receipt.json").write_text(altered.model_dump_json())
    with pytest.raises(OwnershipConflict, match="incarnation"):
        harness.restore("inspect-altered")
    assert harness.backend.calls == 1


def test_expired_operation_stops_before_claim_or_effect(harness: Harness) -> None:
    op = operation(harness.token, "expired")
    op = OperationContext.model_validate(
        {
            **op.model_dump(),
            "deadline": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
    )
    with pytest.raises(OperationStopped):
        harness.executor.restore(harness.token, harness.plan, harness.termination, op)
    assert harness.backend.calls == harness.verifier.calls == 0
    assert not (harness.root / "intent.json").exists()


def test_intent_persistence_failure_prevents_restore(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(intent: RecoveryIntent) -> None:
        raise OSError("intent storage unavailable")

    monkeypatch.setattr(harness.session, "begin", fail)
    with pytest.raises(OSError, match="intent storage"):
        harness.restore()
    assert harness.backend.calls == 0
    assert (harness.root / "state").read_text() == "partial mutation"


def test_backend_exception_keeps_intent_without_false_success(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(
        token: AllocationToken,
        plan: RecoveryPlan,
        control: RecoverySession,
        op: OperationContext,
    ) -> RecoveryResult:
        (harness.root / "state").write_text("partially restored")
        raise OSError("backend interrupted")

    monkeypatch.setattr(harness.backend, "restore", fail)
    with pytest.raises(OSError, match="backend interrupted"):
        harness.restore()
    intent = RecoveryIntent.model_validate_json(
        (harness.root / "intent.json").read_bytes()
    )
    assert intent.allocation == harness.token
    assert not (harness.root / "receipt.json").exists()


def test_terminal_allocation_without_recovery_receipt_cannot_reopen(
    harness: Harness,
) -> None:
    harness.journal.advance(
        harness.token,
        "quarantined",
        harness.termination.evidence,
        1,
        operation(harness.token, "quarantine"),
    )
    with pytest.raises(OwnershipConflict, match="Terminal"):
        harness.restore()
    assert harness.backend.calls == 0


def test_receipt_commit_precedes_quarantine_and_replay_only_finishes_bookkeeping(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness.backend.fail = True
    advance = harness.journal.advance

    def fail_quarantine(
        token: AllocationToken,
        state: ResourceState,
        evidence: tuple[EvidenceRef, ...],
        revision: int,
        op: OperationContext,
    ) -> ResourceRecord:
        if state == "quarantined":
            raise OSError("quarantine record unavailable")
        return advance(token, state, evidence, revision, op)

    monkeypatch.setattr(harness.journal, "advance", fail_quarantine)
    with pytest.raises(OSError, match="quarantine record"):
        harness.restore()
    assert (
        harness.journal.read(
            harness.token, operation(harness.token, "inspect-pending")
        ).state
        == "closing"
    )
    assert (harness.root / "receipt.json").exists()
    monkeypatch.undo()
    assert harness.restore("finish-quarantine").status == "quarantined"
    assert harness.backend.calls == 1
    assert (
        harness.journal.read(
            harness.token, operation(harness.token, "inspect-finished")
        ).state
        == "quarantined"
    )
