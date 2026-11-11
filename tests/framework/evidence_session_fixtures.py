"""Synthetic facts for pure session contracts; never real admission proofs."""

from datetime import datetime, timedelta, timezone
from typing import Literal
from lab_generate_skill.domain.evidence_io import EvidenceCommand
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceSessionCapacity,
    EvidenceWorkerInstance,
    EvidenceOperationIntent,
    EvidenceOperationOutcome,
    EvidenceWorkerEnded,
    EvidenceSessionResolution,
)
from lab_generate_skill.domain.evidence_session_state import (
    EvidenceSessionSnapshot,
    begin_evidence_exchange,
)
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceOwner
from lab_generate_skill.domain.evidence_identity import evidence_reference
from test_filesystem_evidence import metadata

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def binding() -> EvidenceSessionBinding:
    return EvidenceSessionBinding(
        storage_id="store-1",
        scope="source",
        source_task_id="source-1",
        session_id="session-1",
        owner=ResourceOwner(
            run_id="run-1", owner_id="owner-1", job_id="job-1", worker_id="supervisor-1"
        ),
        release_id="release-1",
        storage_config_sha256="a" * 64,
    )


def capacity() -> EvidenceSessionCapacity:
    return EvidenceSessionCapacity(
        max_exchanges=3, max_resolutions_per_exchange=3, max_bytes=100000
    )


def intent(
    index: int = 1, kind: Literal["read", "put"] = "put"
) -> EvidenceOperationIntent:
    return EvidenceOperationIntent(
        exchange_id=f"exchange-{index}",
        operation=OperationContext(
            operation_id=f"io-{index}",
            run_id="run-1",
            owner_id="owner-1",
            attempt_id="attempt-1",
            allocation_id="allocation-1",
            deadline=NOW + timedelta(seconds=10),
        ),
        worker=EvidenceWorkerInstance(
            node_id="node-1",
            boot_id="boot-1",
            process_id=100 + index,
            start_ticks=10000 + index,
        ),
        kind=kind,
        reference=evidence_reference(b"original", metadata()),
        command_sha256="b" * 64,
        command=EvidenceCommand(
            exchange_id=f"exchange-{index}",
            operation=kind,
            root="/unit/evidence",
            max_object_bytes=1024,
            reference=evidence_reference(b"original", metadata()),
            metadata=metadata() if kind == "put" else None,
        ),
        controller=ProcessIdentity(
            node_id="node-1", boot_id="boot-1", process_id=99, start_ticks=9000
        ),
    )


def outcome(
    original: EvidenceOperationIntent, *, succeeded: bool = True
) -> EvidenceOperationOutcome:
    return EvidenceOperationOutcome(
        outcome_id=f"outcome-{original.exchange_id}",
        exchange_id=original.exchange_id,
        operation=original.operation,
        reply_sha256="c" * 64,
        status="succeeded" if succeeded else "failed",
        reason_code=None if succeeded else "MISSING_EVIDENCE",
    )


def resolution(
    original: EvidenceOperationIntent,
    index: int = 1,
    *,
    ended: bool = True,
    object_state: Literal["present", "absent", "unknown"] = "present",
    cleanup_state: Literal["clean", "failed", "unknown"] = "clean",
) -> EvidenceSessionResolution:
    return EvidenceSessionResolution(
        resolution_id=f"resolution-{original.exchange_id}-{index}",
        exchange_id=original.exchange_id,
        operation=original.operation.cleanup(
            f"cleanup-{original.exchange_id}-{index}",
            now=NOW + timedelta(seconds=20),
            seconds=10,
        ),
        worker_end=(
            EvidenceWorkerEnded(
                worker=original.worker,
                observed_at=NOW + timedelta(seconds=21),
                returncode=0,
                verifier_id="unit-verifier",
                proof_sha256="d" * 64,
            )
            if ended
            else None
        ),
        object_state=object_state,
        cleanup_state=cleanup_state,
        reason_code="UNIT_FACTS",
    )


def pending() -> EvidenceSessionSnapshot:
    return begin_evidence_exchange(
        EvidenceSessionSnapshot(binding=binding(), capacity=capacity()), intent(), 0
    )
