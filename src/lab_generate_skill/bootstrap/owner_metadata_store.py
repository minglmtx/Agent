"""Controlled pre-claim evidence on the original physical owner, no task grant.

The caller fixes the existing namespace, roots and installed release explicitly.
The same admission, worker, resolver, operations and durable sessions used by
run/source storage remain in charge. Initialization is still explicit; an old
or uncertain session is never bypassed through a new namespace or fallback.
"""

from dataclasses import dataclass
from lab_generate_skill.adapters.storage.managed_store import ManagedEvidenceStore
from lab_generate_skill.adapters.storage.scope_admission import (
    PinnedSlurmStorageAdmission,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.storage_scope import OwnerMetadataStorageScope
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControls,
    OperationControl,
)
from .evidence_store import assemble_evidence_store


@dataclass(frozen=True)
class OwnerMetadataStore:
    store: ManagedEvidenceStore
    admission: PinnedSlurmStorageAdmission


def owner_metadata_store(
    scope: OwnerMetadataStorageScope,
    activation: OperationContext,
    clock: Clock,
    controls: OperationControls,
    control: OperationControl,
    *,
    max_io_seconds: float,
    cleanup_seconds: float,
) -> OwnerMetadataStore:
    if not isinstance(scope, OwnerMetadataStorageScope):
        raise TypeError("Explicit original owner metadata scope required")
    scope = OwnerMetadataStorageScope.model_validate(scope)
    admission = PinnedSlurmStorageAdmission(scope)
    store = assemble_evidence_store(
        scope.binding,
        scope.config,
        scope.config.installation.python_executable,
        admission,
        clock,
        controls,
        control,
        max_io_seconds=max_io_seconds,
        cleanup_seconds=cleanup_seconds,
    )
    try:
        admission.activate(None, activation, control)
    except BaseException:
        admission.stop_new_io()
        raise
    return OwnerMetadataStore(store, admission)
