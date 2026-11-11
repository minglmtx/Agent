"""Fixed guarded leaf: installation and kernel checks before readonly current I/O."""

import hashlib
import os
from contextlib import nullcontext
from pathlib import Path
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.claims import SourceClaimRecord
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.adapters.processes.owner_pidfd import pinned_owner
from lab_generate_skill.adapters.processes.owner_supervisor import arm_parent_death
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.adapters.releases.installation import (
    verify_release_installation,
)
from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile
from lab_generate_skill.adapters.ledger.claim_snapshot import read_claim_record
from lab_generate_skill.adapters.ledger.stage_validation_snapshot import (
    checked_validation_parent,
)
from lab_generate_skill.adapters.plans.claim_evidence import MAX_CLAIM_BYTES
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_current_cgroup
from .claim_authority import DelegatedClaimAccess
from .claim_protocol import (
    decode_claim_command,
    encode_claim_reply,
    ClaimReadReply,
    ClaimPhase,
    StageValidationClaimReadCommand,
)


def serve_claim_read(raw: bytes, controls: OperationControls) -> bytes:
    command = decode_claim_command(raw)
    control = controls.bind(command.operation)
    control.checkpoint()
    worker = current_process_identity()
    phase: ClaimPhase = "parent_guard"
    installed: InstalledReleaseSources | None = None
    membership: SlurmCgroupMembership | None = None
    record: SourceClaimRecord | None = None
    error = None
    try:
        if os.getppid() != command.scope.writer.process_id:
            raise OwnershipConflict("Claim controller is not the actual parent")
        with pinned_owner(command.scope.writer, control) as parent_fd:
            arm_parent_death(command.scope.writer.process_id)
            phase = "installation"
            installed = verify_release_installation(
                command.scope.config.installation, control
            )
            phase = "membership"
            membership = observe_current_cgroup(
                command.scope.execution, worker, control
            ).membership
            authority = DelegatedClaimAccess(command, worker, parent_fd)
            authority.authorize_access(command.operation, control)
            phase = "read"
            assert command.scope.claim is not None
            root = Path(command.root)
            # Check all ancestors in the child; parent performs no path I/O.
            if root.resolve(strict=True) != root:
                raise OwnershipConflict("Claim root contains a symbolic link")
            validation = (
                command.validation
                if isinstance(command, StageValidationClaimReadCommand)
                else None
            )
            filename = (
                command.scope.claim.key.filename
                if validation is None
                else validation.filename
            )
            with AtomicSnapshotFile(root, filename, max_bytes=MAX_CLAIM_BYTES).locked(
                control, create_lock=False
            ) as transaction:
                with (
                    nullcontext()
                    if validation is None
                    else checked_validation_parent(root, validation, control)
                ):
                    record = read_claim_record(
                        transaction, command.scope.claim.key, command.operation
                    )
                    if record.binding != command.scope.claim:
                        raise OwnershipConflict(
                            "Claim differs from complete original source"
                        )
                    authority.authorize_access(command.operation, control)
            phase = "verification"
            authority.authorize_access(command.operation, control)
            after = observe_current_cgroup(
                command.scope.execution, worker, control
            ).membership
            if after != membership:
                raise OwnershipConflict("Claim worker left original Slurm membership")
            phase = "completion"
            control.checkpoint()
        control.checkpoint()
    except BaseException as caught:
        error = describe_error(caught)
    return encode_claim_reply(
        ClaimReadReply(
            command_sha256=hashlib.sha256(raw).hexdigest(),
            worker=worker,
            phase=phase,
            error=error,
            installed_sources=installed,
            membership=membership,
            record=record,
        )
    )
