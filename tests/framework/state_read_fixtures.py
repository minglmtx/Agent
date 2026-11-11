"""Actual Slurm reader/installation; fixture facts grant no site permission."""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import shutil
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.state_read_checks import SupervisedStateChecks
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.bootstrap.owner_metadata_store import (
    owner_metadata_store,
    OwnerMetadataStore,
)
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceOwner
from lab_generate_skill.domain.storage_scope import OwnerMetadataStorageScope
from lab_generate_skill.runtime.lifecycle import OperationGuards
from installed_source_fixtures import InstalledFixture
from registered_storage_fixtures import request
from test_linux_cgroups import actual_slurm_execution
from test_resource_journal import NoCancellation

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")


@dataclass
class StateReadCase:
    current: OwnerMetadataStore
    scope: OwnerMetadataStorageScope
    operation: OperationContext
    controls: OperationGuards
    checks: SupervisedStateChecks


def reader_case(
    root: Path,
    evidence_root: Path,
    task: TaskIdentity,
    installed: InstalledFixture,
) -> StateReadCase:
    execution, _ = actual_slurm_execution()
    (root / "sessions").mkdir(parents=True, mode=0o700)
    # The original native fixture lives on this node. Stage immutable copies
    # into this test's workspace CAS; do not widen production root checks or
    # mutate the fixture's original namespace/history.
    staged = root / "data"
    shutil.copytree(evidence_root / "blobs", staged / "blobs")
    original = request(root, create=True, installation=installed)
    config = EvidenceStorageConfig.model_validate(
        original.config.model_copy(
            update={
                "evidence_root": str(staged),
                "max_object_bytes": 64 * 1024**2,
            }
        )
    )
    owner = ResourceOwner(
        run_id="state-proof-review-" + execution.job_id,
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
        workspace_root=str(W),
    )
    clock = SystemClock()
    controls = OperationGuards(clock, NoCancellation())
    operation = OperationContext(
        operation_id="state-proof-review",
        run_id=owner.run_id,
        owner_id=owner.owner_id,
        deadline=clock.utcnow() + timedelta(seconds=180),
    )
    current = owner_metadata_store(
        scope,
        operation,
        clock,
        controls,
        controls.bind(operation),
        max_io_seconds=30,
        cleanup_seconds=60,
    )
    current.store.initialize(controls.bind(operation))
    checks = SupervisedStateChecks(scope, current.store, current.admission, task)
    return StateReadCase(current, scope, operation, controls, checks)
