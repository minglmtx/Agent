"""Fixed guarded create/exchange service; all filesystem work stays in child.

No recovery, deletion, retries or dynamic providers. Actual parent incarnation
is pinned and kernel parent-death SIGKILL armed before any storage operation.
The service creates no descendants. Independent closure/resolution is separate.
"""

import hashlib
import os
from pathlib import Path
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.adapters.ledger.evidence_sessions import FileEvidenceSessions
from lab_generate_skill.adapters.processes.owner_pidfd import pinned_owner
from lab_generate_skill.adapters.processes.owner_supervisor import arm_parent_death
from lab_generate_skill.adapters.processes.worker_identity import (
    current_evidence_worker,
)
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from .registered_protocol import (
    RegisteredStorageReply,
    decode_registered_command,
    encode_registered_reply,
)
from .registered_authority import DelegatedStorageAuthority
from .registered_exchange_result import (
    retained_registered_exchange,
    RegisteredExchangeObservation,
)
from .physical_exchange import PhysicalEvidenceExchange
from .session_exchange import registered_exchange
from .worker_protocol import encode_command
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.adapters.releases.installation import (
    verify_release_installation,
)


def serve_registered_storage(raw: bytes, controls: OperationControls) -> bytes:
    command, payload = decode_registered_command(raw)
    control = controls.bind(command.operation)
    control.checkpoint()
    worker = current_evidence_worker()
    phase = "parent_guard"
    observation = RegisteredExchangeObservation(phase, None, None, None)
    snapshot: EvidenceSessionSnapshot | None = None
    error = None
    installed_sources: InstalledReleaseSources | None = None
    try:
        if os.getppid() != command.controller.process_id:
            raise OwnershipConflict("Storage controller is not the actual parent")
        with pinned_owner(command.controller, control) as parent_fd:
            arm_parent_death(command.controller.process_id)
            phase = "installation"
            installed_sources = verify_release_installation(
                command.config.installation, control
            )
            phase = "configuration"
            for name in (command.config.evidence_root, command.config.session_root):
                root = Path(name)
                if root.resolve(strict=True) != root or not root.is_dir():
                    raise OwnershipConflict(
                        "Storage roots must be provisioned canonical directories"
                    )
                control.checkpoint()
            inner = None if command.io is None else encode_command(command.io, payload)
            physical = None if inner is None else PhysicalEvidenceExchange(inner)
            authority = DelegatedStorageAuthority(
                command, worker, parent_fd, control, physical
            )
            ledger = FileEvidenceSessions(
                Path(command.config.session_root),
                command.config.storage_id,
                command.config.sha256,
                controls,
                authority,
            )
            if command.action == "create":
                phase = "creation"
                snapshot = ledger.create(
                    command.binding, command.config.capacity, command.operation
                )
            elif command.action == "open_existing":
                phase = "existing_namespace_read"
                snapshot = ledger.read(command.binding, command.operation)
                if (
                    snapshot.capacity != command.config.capacity
                    or not snapshot.entries
                    or not snapshot.entries[-1].reusable
                ):
                    raise OwnershipConflict(
                        "Existing source namespace is empty, changed or unresolved"
                    )
            else:
                assert (
                    inner is not None
                    and physical is not None
                    and command.expected_revision is not None
                )
                phase = "registered_exchange"
                result = registered_exchange(
                    inner,
                    command.binding,
                    command.expected_revision,
                    ledger,
                    command.operation,
                    controls,
                    physical,
                    controller=command.controller,
                )
                snapshot = result.snapshot
                observation = RegisteredExchangeObservation(
                    "completion", result.intent, result.reply, result.outcome
                )
            phase = "completion"
            control.checkpoint()
        control.checkpoint()
    except BaseException as caught:
        error = describe_error(caught)
        snapshot = None
        original = retained_registered_exchange(caught)
        if original is not None:
            observation, phase = original, original.phase
    return encode_registered_reply(
        RegisteredStorageReply(
            schema_version=(
                "registered-storage-reply/4"
                if command.action == "open_existing"
                else "registered-storage-reply/3"
            ),
            command_sha256=hashlib.sha256(raw).hexdigest(),
            worker=worker,
            phase=phase,
            error=error,
            installed_sources=installed_sources,
            intent=observation.intent,
            outcome=observation.outcome,
        ),
        snapshot,
        observation.reply or b"",
    )
