"""Independent fixed leaf: read original intent, verify ending, inspect, record."""

import hashlib
import os
from pathlib import Path
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.storage_unregistered import StorageUnregisteredExchange
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionResolution
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.adapters.ledger.evidence_sessions import FileEvidenceSessions
from lab_generate_skill.adapters.processes.owner_pidfd import pinned_owner
from lab_generate_skill.adapters.processes.owner_supervisor import arm_parent_death
from lab_generate_skill.adapters.processes.worker_identity import (
    current_evidence_worker,
)
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from .resolver_protocol import (
    decode_resolution_command,
    encode_resolution_reply,
    StorageResolutionReply,
)
from .resolver_authority import StorageResolverAuthority
from .observed_inspection import ObservedStorageInspection
from .session_resolution import resolve_registered_storage
from .resolution_result import retained_storage_resolution
from .worker_protocol import encode_command
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.adapters.releases.installation import (
    verify_release_installation,
)


def serve_storage_resolution(raw: bytes, controls: OperationControls) -> bytes:
    command, payload = decode_resolution_command(raw)
    original = command.original
    assert original.io is not None
    control = controls.bind(command.cleanup)
    control.checkpoint()
    worker = current_evidence_worker()
    phase = "parent_guard"
    error = None
    installed_sources: InstalledReleaseSources | None = None
    snapshot: EvidenceSessionSnapshot | None = None
    resolution: EvidenceSessionResolution | None = None
    not_registered: StorageUnregisteredExchange | None = None
    try:
        if os.getppid() != original.controller.process_id:
            raise OwnershipConflict("Resolver controller is not actual parent")
        with pinned_owner(original.controller, control) as fd:
            arm_parent_death(original.controller.process_id)
            phase = "installation"
            installed_sources = verify_release_installation(
                original.config.installation, control
            )
            inspection = ObservedStorageInspection(original.io)
            authority = StorageResolverAuthority(
                command, worker, fd, control, inspection
            )
            ledger = FileEvidenceSessions(
                Path(original.config.session_root),
                original.config.storage_id,
                original.config.sha256,
                controls,
                authority,
            )
            phase = "original_history"
            before = ledger.read(original.binding, command.cleanup)
            entry = next(
                (
                    e
                    for e in before.entries
                    if e.intent.exchange_id == original.io.exchange_id
                ),
                None,
            )
            if entry is None:
                not_registered = authority.observe_unregistered(before)
                snapshot = before
            else:
                inner = encode_command(original.io, payload)
                if (
                    entry.intent.command_sha256 != hashlib.sha256(inner).hexdigest()
                    or entry.intent.reference != original.io.reference
                    or entry.intent.kind != original.io.operation
                ):
                    raise OwnershipConflict(
                        "Resolver command differs from durable original"
                    )
                phase = "original_termination"
                end = authority.prepare(
                    entry.intent,
                    replay=any(
                        r.operation == command.cleanup for r in entry.resolutions
                    ),
                )
                phase = "resolution"
                result = resolve_registered_storage(
                    inner,
                    original.binding,
                    ledger,
                    command.cleanup,
                    controls,
                    end,
                    inspection,
                )
                resolution, snapshot = result.resolution, result.snapshot
            phase = "completion"
            control.checkpoint()
        control.checkpoint()
    except BaseException as caught:
        error = describe_error(caught)
        snapshot = None
        not_registered = None
        retained = retained_storage_resolution(caught)
        if retained is not None:
            resolution = retained.resolution
    reply = StorageResolutionReply(
        request_sha256=hashlib.sha256(raw).hexdigest(),
        worker=worker,
        phase=phase,
        error=error,
        installed_sources=installed_sources,
        resolution=resolution,
    )
    if not_registered is not None:
        reply = StorageResolutionReply.model_validate(
            reply.model_copy(
                update={
                    "schema_version": "storage-resolution-reply/4",
                    "not_registered": not_registered,
                }
            )
        )
    return encode_resolution_reply(
        reply,
        snapshot,
    )
