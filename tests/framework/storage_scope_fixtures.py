"""Synthetic scope inputs; actual kernel/claim/installed tests are separate."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from lab_generate_skill.domain.storage_scope import StorageScope
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.claims import SourceClaimBinding
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.adapters.slurm.linux_cgroups import KernelCgroupObservation
from lab_generate_skill.adapters.slurm.kernel_capture import KernelCapture
from registered_storage_fixtures import request
from test_run_plan import reference, plan
from test_slurm_probe import execution
from cgroup_fixtures import writer, USER


def scope(*, source: bool = False) -> StorageScope:
    cmd = request(Path("/unit/state"), create=True)
    config = cmd.config
    owner = cmd.binding.owner.model_copy(update={"job_id": execution().job_id})
    run = RunBinding(
        owner=owner,
        plan_ref=reference("run-plan/3"),
        release_ref=config.installation.manifest_ref,
        submission_key="submission",
    )
    task = plan().tasks[0]
    claim = (
        SourceClaimBinding(scope_id="claims", run=run, task=task) if source else None
    )
    binding = cmd.binding.model_copy(
        update={
            "scope": "source" if source else "run",
            "source_task_id": task.identity.source_task_id if source else None,
            "owner": owner,
        }
    )
    return StorageScope(
        binding=binding,
        config=config,
        run=run,
        writer=writer(),
        execution=execution(),
        workspace_root="/unit",
        claim=claim,
    )


def operation(bound: StorageScope, name: str = "activate") -> OperationContext:
    return OperationContext(
        operation_id=name,
        run_id=bound.run.owner.run_id,
        owner_id=bound.run.owner.owner_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=90),
    )


def observation(bound: StorageScope) -> KernelCgroupObservation:
    return KernelCgroupObservation(
        SlurmCgroupMembership(
            job_id=bound.execution.raw_job_id,
            step_id="batch",
            writer=bound.writer,
            uid=bound.execution.uid,
            user_path=USER,
            mount_id=138,
            device=26,
            user_inode=1234,
            task_inode=5678,
        ),
        KernelCapture((), ()),
    )
