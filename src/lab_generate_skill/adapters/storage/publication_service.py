"""Fixed guarded leaf: installation and kernel checks before readonly current I/O."""

import hashlib
import os
from pathlib import Path
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
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
from lab_generate_skill.adapters.releases.current import FileReleaseCurrent
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_current_cgroup
from .publication_authority import DelegatedPublicationAccess
from .publication_protocol import (
    decode_publication_command,
    encode_publication_reply,
    PublicationReadReply,
    PublicationPhase,
)


def serve_publication_read(raw: bytes, controls: OperationControls) -> bytes:
    command = decode_publication_command(raw)
    control = controls.bind(command.operation)
    control.checkpoint()
    worker = current_process_identity()
    phase: PublicationPhase = "parent_guard"
    installed: InstalledReleaseSources | None = None
    membership: SlurmCgroupMembership | None = None
    snapshot: ReleaseCurrentSnapshot | None = None
    error = None
    try:
        if os.getppid() != command.scope.writer.process_id:
            raise OwnershipConflict("Publication controller is not the actual parent")
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
            authority = DelegatedPublicationAccess(command, worker, parent_fd)
            authority.authorize_access(command.deployment, command.operation, control)
            phase = "read"
            snapshot = FileReleaseCurrent(
                Path(command.root), command.deployment, controls, authority
            ).read(command.operation)
            phase = "verification"
            authority.authorize_access(command.deployment, command.operation, control)
            after = observe_current_cgroup(
                command.scope.execution, worker, control
            ).membership
            if after != membership:
                raise OwnershipConflict(
                    "Publication worker left original Slurm membership"
                )
            phase = "completion"
            control.checkpoint()
        control.checkpoint()
    except BaseException as caught:
        error = describe_error(caught)
    return encode_publication_reply(
        PublicationReadReply(
            command_sha256=hashlib.sha256(raw).hexdigest(),
            worker=worker,
            phase=phase,
            error=error,
            installed_sources=installed,
            membership=membership,
            snapshot=snapshot,
        )
    )
