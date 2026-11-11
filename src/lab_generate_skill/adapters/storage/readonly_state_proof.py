"""Original ready namespace under its actual parent's bounded fixed worker.

This reuses the existing readonly session and parent protection primitives.
The caller receives no publication or native action capability.
"""

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
from lab_generate_skill.adapters.ledger.evidence_sessions import FileEvidenceSessions
from lab_generate_skill.adapters.processes.owner_pidfd import pinned_owner, ended
from lab_generate_skill.adapters.processes.owner_supervisor import arm_parent_death
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.releases.installation import (
    verify_release_installation,
)
from lab_generate_skill.domain.evidence_read_scope import EvidenceReadScope
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from .readonly_evidence import ReadOnlyEvidence
from .readonly_session import ReadOnlySessionAuthority


@contextmanager
def original_state_proof(
    scope: EvidenceReadScope,
    workspace: Path,
    controls: OperationControls,
    control: OperationControl,
) -> Iterator[tuple[ReadOnlyEvidence, InstalledReleaseSources]]:
    control.checkpoint()
    if os.getppid() != scope.controller.process_id:
        raise OwnershipConflict("State proof controller is not the actual parent")
    with pinned_owner(scope.controller, control) as parent:
        arm_parent_death(scope.controller.process_id)
        installed = verify_release_installation(scope.config.installation, control)
        worker = current_process_identity()
        sessions = FileEvidenceSessions(
            Path(scope.config.session_root),
            scope.config.storage_id,
            scope.config.sha256,
            controls,
            ReadOnlySessionAuthority(scope, worker, parent, control),
        )
        before = sessions.read(scope.binding, scope.operation)
        if (
            before.revision != scope.revision
            or before.capacity != scope.config.capacity
            or (before.entries and not before.entries[-1].reusable)
        ):
            raise OwnershipConflict("Original state proof namespace is unresolved")
        root = Path(scope.config.evidence_root)
        if (
            workspace.resolve(strict=True) != workspace
            or root.resolve(strict=True) != root
            or not root.is_dir()
            or root == workspace
            or not root.is_relative_to(workspace)
        ):
            raise OwnershipConflict("State proof root left its original workspace")
        evidence = ReadOnlyEvidence(
            root,
            max_object_bytes=scope.config.max_object_bytes,
            reuse_within_proof=True,
        )
        yield evidence, installed
        control.checkpoint()
        if sessions.read(scope.binding, scope.operation) != before:
            raise OwnershipConflict("Original namespace changed during state proof")
        if ended(parent) or os.getppid() != scope.controller.process_id:
            raise OwnershipConflict("Original controller ended during state proof")
