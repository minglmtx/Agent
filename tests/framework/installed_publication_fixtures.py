"""Actual installed storage reader and current files; publisher remains a fixture."""

import os
from pathlib import Path
from lab_generate_skill.domain.storage_scope import StorageScope
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.storage_launch import StorageLaunch
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
from lab_generate_skill.adapters.storage.publication_protocol import (
    PublicationReadCommand,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from installed_source_fixtures import InstalledFixture
from registered_storage_fixtures import request
from storage_launch_fixtures import selection
from storage_scope_fixtures import operation
from test_linux_cgroups import actual_slurm_execution
from test_run_plan import reference
from release_current_fixtures import store


def setup(
    root: Path, installed: InstalledFixture, *, publish: bool = True
) -> tuple[StorageLaunch, ReleaseCurrentSnapshot, PublicationReadCommand]:
    execution, _ = actual_slurm_execution()
    original = request(root / "storage", create=True, installation=installed)
    owner = original.binding.owner.model_copy(update={"job_id": execution.job_id})
    run = RunBinding(
        owner=owner,
        plan_ref=reference("run-plan/3"),
        release_ref=original.config.installation.manifest_ref,
        submission_key="engineering",
    )
    binding = original.binding.model_copy(
        update={"owner": owner, "scope": "run", "source_task_id": None}
    )
    scope = StorageScope(
        binding=binding,
        config=original.config,
        run=run,
        writer=current_process_identity(),
        execution=execution,
        workspace_root=os.path.commonpath([str(root), str(installed.workspace)]),
        claim=None,
    )
    launch, snapshot = selection(scope)
    current = root / "current"
    current.mkdir()
    if publish:
        publisher = store(current)
        publisher.initialize(snapshot.initialized_by)
        publisher.activate(snapshot.switches[0])
    command = PublicationReadCommand(
        scope=launch.scope,
        deployment=launch.deployment,
        root=str(current),
        operation=operation(launch.scope),
    )
    return launch, snapshot, command
