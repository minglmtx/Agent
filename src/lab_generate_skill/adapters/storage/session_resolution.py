"""Inspect and record an original exchange, never replay read/put or unlink.

This entire composition runs inside external supervision, including session
reads, authority and filesystem inspection. EvidenceSessions must enforce its
mandatory real authority: supplied worker_end is only a proposed fact, not
proof accepted here. The owner/resolver bootstrap remains a separate boundary.
Unknown termination skips data inspection and persists isolation. Existing
temporary files remain untouched until independent ownership permits cleanup.
"""

import hashlib
from typing import Literal
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceSessionResolution,
    EvidenceWorkerEnded,
    check_evidence_cleanup,
)
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.ports.evidence_sessions import EvidenceSessions
from lab_generate_skill.ports.lifecycle import OperationControls
from .observed_inspection import ObservedStorageInspection
from .inspection_result import StorageInspectionFailure, StorageObservation
from .resolution_result import RegisteredStorageResolution, StorageResolutionFailure
from .worker_protocol import decode_command


def resolve_registered_storage(
    raw: bytes,
    binding: EvidenceSessionBinding,
    sessions: EvidenceSessions,
    cleanup: OperationContext,
    controls: OperationControls,
    worker_end: EvidenceWorkerEnded | None,
    inspection: ObservedStorageInspection,
) -> RegisteredStorageResolution:
    command, _ = decode_command(raw)
    if inspection.command != command:
        raise OwnershipConflict("Inspection belongs to another original command")
    binding = EvidenceSessionBinding.model_validate(binding)
    cleanup = OperationContext.model_validate(cleanup)
    if cleanup.mode != "cleanup":
        raise OwnershipConflict("Storage resolution requires linked cleanup")
    if worker_end is not None:
        worker_end = EvidenceWorkerEnded.model_validate(worker_end)
    control = controls.bind(cleanup)
    control.checkpoint()
    before = EvidenceSessionSnapshot.model_validate(sessions.read(binding, cleanup))
    if before.binding != binding:
        raise OwnershipConflict("Original session read returned another binding")
    entry = next(
        (e for e in before.entries if e.intent.exchange_id == command.exchange_id), None
    )
    if entry is None:
        raise EvidenceNotFound(
            "Original exchange is missing; resolution cannot create it"
        )
    intent = entry.intent
    check_evidence_cleanup(intent.operation, cleanup)
    if (
        intent.command != command
        or intent.command_sha256 != hashlib.sha256(raw).hexdigest()
        or intent.reference != command.reference
        or intent.kind != command.operation
        or (worker_end is not None and worker_end.worker != intent.worker)
    ):
        raise OwnershipConflict("Resolution differs from original command or worker")
    resolution_id = (
        "resolve-" + hashlib.sha256(cleanup.operation_id.encode()).hexdigest()
    )
    for prior in entry.resolutions:
        if prior.resolution_id == resolution_id:
            if prior.operation != cleanup or prior.worker_end != worker_end:
                raise OwnershipConflict("Original resolution is bound to other facts")
            control.checkpoint()
            return RegisteredStorageResolution(prior, None, before)
    if entry is not before.entries[-1] or entry.reusable:
        raise InvalidTransition("Resolved exchange cannot acquire new cleanup facts")
    observation: StorageObservation | None = None
    first: BaseException | None = None
    object_state: Literal["present", "absent", "unknown"] = "unknown"
    cleanup_state: Literal["clean", "failed", "unknown"] = "unknown"
    reason = "WORKER_TERMINATION_UNCONFIRMED"
    if worker_end is not None:
        try:
            observation = inspection.inspect(command, control)
            object_state = observation.object_state
            cleanup_state = (
                "clean"
                if observation.temporary_state in ("absent", "not_applicable")
                else "failed"
            )
            reason = (
                "STORAGE_OBSERVED"
                if cleanup_state == "clean"
                else "TEMPORARY_REMAINS_UNTOUCHED"
            )
        except BaseException as error:
            first = error
            observation = (
                error.observation
                if isinstance(error, StorageInspectionFailure)
                else getattr(error, "storage_inspection", None)
            )
            # Partial reads and a failed directory recheck never become clean.
            reason = "STORAGE_INSPECTION_FAILED"
    resolution = EvidenceSessionResolution(
        resolution_id=resolution_id,
        exchange_id=command.exchange_id,
        operation=cleanup,
        worker_end=worker_end,
        object_state=object_state,
        cleanup_state=cleanup_state,
        reason_code=reason,
    )
    committed: EvidenceSessionSnapshot | None = None
    try:
        control.checkpoint()
        candidate = EvidenceSessionSnapshot.model_validate(
            sessions.resolve(binding, resolution, before.revision)
        )
        actual = next(
            (
                e
                for e in candidate.entries
                if e.intent.exchange_id == command.exchange_id
            ),
            None,
        )
        if (
            candidate.binding != binding
            or candidate.capacity != before.capacity
            or candidate.revision != before.revision + 1
            or actual is None
            or actual.intent != entry.intent
            or actual.outcome != entry.outcome
            or actual.resolutions != (*entry.resolutions, resolution)
            or candidate.entries[:-1] != before.entries[:-1]
        ):
            raise EvidenceIntegrityError(
                "Resolution acknowledgement differs from exact original facts"
            )
        committed = candidate
        control.checkpoint()
    except BaseException as error:
        if first is not None:
            first = BaseExceptionGroup(
                "Storage inspection and recording failed", [first, error]
            )
        else:
            first = error
    result = RegisteredStorageResolution(resolution, observation, committed)
    if first is not None:
        if isinstance(first, OperationStopped) or not isinstance(first, Exception):
            setattr(first, "storage_resolution", result)
            raise first
        raise StorageResolutionFailure(result) from first
    return result
