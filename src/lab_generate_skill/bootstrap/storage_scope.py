"""Explicit storage capability assembly; initialize is a separate caller action."""

from dataclasses import dataclass
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.storage_launch import StorageLaunch
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
from lab_generate_skill.application.storage_launch import StorageLaunchGate
from lab_generate_skill.ports.release_current import ReleaseCurrentReader
from lab_generate_skill.ports.claims import SourceClaimReader
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControl,
    OperationControls,
)
from lab_generate_skill.adapters.storage.managed_store import ManagedEvidenceStore
from lab_generate_skill.adapters.storage.scope_admission import (
    PinnedSlurmStorageAdmission,
)
from .evidence_store import assemble_evidence_store


@dataclass(frozen=True)
class ScopedEvidenceStore:
    store: ManagedEvidenceStore
    admission: PinnedSlurmStorageAdmission
    launch: StorageLaunch
    publication: ReleaseCurrentSnapshot


def assemble_slurm_evidence_store(
    launch: StorageLaunch,
    current: ReleaseCurrentReader,
    claims: SourceClaimReader | None,
    activation: OperationContext,
    clock: Clock,
    cleanup_controls: OperationControls,
    control: OperationControl,
    *,
    max_io_seconds: float,
    cleanup_seconds: float,
) -> ScopedEvidenceStore:
    """Validate inline plan/publication selection before scope activation.

    A source uses existing control-plane claims; never this uninitialized store.
    The returned capability is storage-only, not production experiment approval.
    """
    launch = StorageLaunch.model_validate(launch)
    scope = launch.scope
    admission = PinnedSlurmStorageAdmission(scope)
    store = assemble_evidence_store(
        scope.binding,
        scope.config,
        scope.config.installation.python_executable,
        admission,
        clock,
        cleanup_controls,
        control,
        max_io_seconds=max_io_seconds,
        cleanup_seconds=cleanup_seconds,
    )
    gate = StorageLaunchGate(launch, current)
    observed: ReleaseCurrentSnapshot | None = None
    try:
        observed = gate.observe(activation, control)
        admission.activate(claims, activation, control)
        gate.confirm(observed, activation, control)
    except BaseException as error:
        admission.stop_new_io()
        error.storage_publication = observed  # type: ignore[attr-defined]
        raise
    return ScopedEvidenceStore(store, admission, launch, observed)
