"""Explicit synthetic business scope for real controlled-store engineering tests."""

from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.storage.managed_store import ManagedEvidenceStore
from lab_generate_skill.bootstrap.evidence_store import assemble_evidence_store
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    check_evidence_cleanup,
)
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.storage_termination import StorageProcessEnd
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from registered_storage_fixtures import request, roots
from installed_source_fixtures import InstalledFixture
from storage_installation_fixtures import storage_installation
from test_slurm_commands import Cancel, guard


class EngineeringAdmission:
    def __init__(
        self, binding: EvidenceSessionBinding, config: EvidenceStorageConfig
    ) -> None:
        self.binding, self.config = binding, config
        self.calls: list[OperationContext] = []
        self.denied = False

    def authorize_storage(
        self,
        binding: EvidenceSessionBinding,
        config: EvidenceStorageConfig,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        assert binding == self.binding and config == self.config
        assert (operation.run_id, operation.owner_id) == (
            binding.owner.run_id,
            binding.owner.owner_id,
        )
        if self.denied:
            raise PermissionError("synthetic scope denied")
        control.checkpoint()
        self.calls.append(operation)

    def authorize_cleanup(
        self,
        binding: EvidenceSessionBinding,
        config: EvidenceStorageConfig,
        original: OperationContext,
        cleanup: OperationContext,
        ending: StorageProcessEnd | None,
        control: OperationControl,
    ) -> None:
        assert binding == self.binding and config == self.config
        assert original in self.calls
        check_evidence_cleanup(original, cleanup)
        control.checkpoint()
        self.calls.append(cleanup)


def assembled(
    root: Path,
    python: Path | InstalledFixture,
    *,
    provision: bool = True,
    cleanup_seconds: float = 60,
    max_object_bytes: int = 1024,
    source_task_id: str | None = None,
) -> tuple[ManagedEvidenceStore, EngineeringAdmission]:
    installed = python if isinstance(python, InstalledFixture) else None
    executable = python.executable if isinstance(python, InstalledFixture) else python
    cmd = request(root, create=True, installation=installed)
    config = cmd.config.model_copy(
        update={
            "installation": storage_installation(installed, python=executable),
            "max_object_bytes": max_object_bytes,
            "capacity": cmd.config.capacity.model_copy(
                update={"max_exchanges": 20, "max_bytes": 1000000}
            ),
        }
    )
    binding = cmd.binding.model_copy(update={"storage_config_sha256": config.sha256})
    if source_task_id is not None:
        binding = binding.model_copy(update={"source_task_id": source_task_id})
    admission = EngineeringAdmission(binding, config)
    clock = SystemClock()
    store = assemble_evidence_store(
        binding,
        config,
        str(executable),
        admission,
        clock,
        OperationGuards(clock, Cancel()),
        guard(60),
        max_io_seconds=60,
        cleanup_seconds=cleanup_seconds,
    )
    if provision:
        roots(root)
    return store, admission
