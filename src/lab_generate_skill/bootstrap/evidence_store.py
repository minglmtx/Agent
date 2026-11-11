"""Compose the controlled storage port; caller must explicitly initialize it.

Trusted bootstrap supplies binding, fixed Python, preprovisioned canonical roots
and mandatory admission. No synthetic authority, environment or old-path fallback.
The assembly does not itself prove production release or run/source entitlement.
"""

from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence_storage import EvidenceStorageAdmission
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControl,
    OperationControls,
)
from lab_generate_skill.runtime.evidence_operations import EvidenceOperations
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.storage.managed_store import ManagedEvidenceStore
from lab_generate_skill.adapters.storage.registered_transport import (
    RegisteredStorageTransport,
)
from lab_generate_skill.adapters.storage.resolver_transport import (
    StorageResolverTransport,
)


def assemble_evidence_store(
    binding: EvidenceSessionBinding,
    config: EvidenceStorageConfig,
    python_executable: str,
    admission: EvidenceStorageAdmission,
    clock: Clock,
    cleanup_controls: OperationControls,
    control: OperationControl,
    *,
    max_io_seconds: float,
    cleanup_seconds: float,
) -> ManagedEvidenceStore:
    config = EvidenceStorageConfig.model_validate(config)
    if python_executable != config.installation.python_executable:
        raise OwnershipConflict("Storage launch differs from frozen installation")
    control.checkpoint()
    controller = current_process_identity()
    control.checkpoint()
    return ManagedEvidenceStore(
        binding,
        config,
        controller,
        EvidenceOperations(binding, clock, max_io_seconds=max_io_seconds),
        RegisteredStorageTransport(python_executable, admission),
        StorageResolverTransport(python_executable, admission),
        clock,
        cleanup_controls,
        cleanup_seconds=cleanup_seconds,
    )
