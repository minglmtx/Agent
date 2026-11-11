"""Actual Slurm readonly proof fixture; historical CAS never receives writes."""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.bootstrap.owner_metadata_store import (
    owner_metadata_store,
    OwnerMetadataStore,
)
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.storage_scope import OwnerMetadataStorageScope
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceOwner
from lab_generate_skill.domain.closed_source_read import ClosedMapReadMaterial
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_resource_journal import NoCancellation
from test_linux_cgroups import actual_slurm_execution
from registered_storage_fixtures import request
from installed_source_fixtures import InstalledFixture
from test_closed_source_read_protocol import original_material, E


@dataclass
class ReadCase:
    material: ClosedMapReadMaterial
    current: OwnerMetadataStore
    scope: OwnerMetadataStorageScope
    op: OperationContext
    controls: OperationGuards
    transport: ClosedSourceReadTransport
    clock: SystemClock


def actual_read_case(
    tmp_path: Path,
    installed_sources: InstalledFixture,
    *,
    fresh_cas: bool = False,
    retained: tuple[ClosedMapReadMaterial, Path] | None = None,
) -> ReadCase:
    material, original_root = original_material() if retained is None else retained
    execution, _ = actual_slurm_execution()
    (tmp_path / "sessions").mkdir(mode=0o700)
    if fresh_cas:
        original_root = tmp_path / "data"
        (original_root / "blobs").mkdir(parents=True)
    original = request(tmp_path, create=True, installation=installed_sources)
    config = EvidenceStorageConfig.model_validate(
        original.config.model_copy(
            update={
                "evidence_root": str(original_root),
                "max_object_bytes": 64 * 1024**2,
            }
        )
    )
    owner = ResourceOwner(
        run_id="source-proof-review-" + execution.job_id,
        owner_id="readonly-review",
        job_id=execution.job_id,
        worker_id="original-review-controller",
    )
    binding = EvidenceSessionBinding.model_validate(
        original.binding.model_copy(
            update={
                "scope": "run",
                "source_task_id": None,
                "owner": owner,
                "storage_config_sha256": config.sha256,
            }
        )
    )
    scope = OwnerMetadataStorageScope(
        binding=binding,
        config=config,
        writer=current_process_identity(),
        execution=execution,
        workspace_root=str(E.parents[1]),
    )
    clock = SystemClock()
    controls = OperationGuards(clock, NoCancellation())
    op = OperationContext(
        operation_id="historical-readonly-source-proof",
        run_id=owner.run_id,
        owner_id=owner.owner_id,
        deadline=clock.utcnow() + timedelta(seconds=180),
    )
    current = owner_metadata_store(
        scope,
        op,
        clock,
        controls,
        controls.bind(op),
        max_io_seconds=30,
        cleanup_seconds=60,
    )
    current.store.initialize(controls.bind(op))
    transport = ClosedSourceReadTransport(scope, current.store, current.admission)
    return ReadCase(material, current, scope, op, controls, transport, clock)
