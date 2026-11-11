"""Recorded controller facts; synthetic DBIndex is not an accounting proof."""

import json
from pathlib import Path
from typing import Any

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import AllocationToken, ResourceOwner
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.domain.slurm_step import SlurmStepTarget

FIXTURES = Path(__file__).parent / "fixtures/slurm-step-4752096"


def target() -> SlurmStepTarget:
    execution = SlurmExecutionIdentity(
        cluster="alex",
        job_id="4752096",
        raw_job_id="4752096",
        database_index="999",
        uid=215829,
        submitted_at_epoch=1793034300,
        started_at_epoch=1793034310,
        restart_count=0,
    )
    launcher = ProcessIdentity(
        node_id="a0535",
        boot_id="a67f5993-95b0-4618-8a2c-e79bbf66a1c5",
        process_id=2949041,
        start_ticks=55741650,
    )
    worker = SlurmCgroupMembership(
        job_id=execution.raw_job_id,
        step_id="0",
        writer=launcher.model_copy(
            update={"process_id": 2949064, "start_ticks": 55741658}
        ),
        uid=215829,
        user_path="/sys/fs/cgroup/system.slice/slurmstepd.scope/job_4752096/step_0/user",
        mount_id=138,
        device=26,
        user_inode=233952,
        task_inode=233953,
    )
    return SlurmStepTarget(
        resources="single_gpu",
        execution=execution,
        step_name="lab-generator-step-proof-4752096",
        launcher=launcher,
        worker=worker,
    )


def token() -> AllocationToken:
    t = target()
    return AllocationToken(
        allocation_id="unit-allocation",
        owner=ResourceOwner(
            run_id="run",
            owner_id="owner",
            job_id=t.execution.job_id,
            worker_id="parent",
        ),
        scope="batch",
        resource_kind="generator",
        expected_resource_id="generator",
        provider_id="fixed-generator-worker",
        provider_version="2",
        recovery_ref=EvidenceRef(
            uri="memory:unit",
            sha256="a" * 64,
            size_bytes=1,
            media_type="application/json",
            content_schema="recovery-plan/1",
            visibility="private",
            producer="test",
        ),
    )


def recorded() -> dict[str, Any]:
    value: object = json.loads((FIXTURES / "running.json").read_bytes())
    assert isinstance(value, dict)
    return value


def encoded(value: dict[str, Any]) -> bytes:
    return json.dumps(value).encode()


def epoch_text() -> bytes:
    """Explicit synthetic epoch variant; original recorded bytes stay unchanged."""
    return (
        (FIXTURES / "running.txt")
        .read_bytes()
        .replace(b"StartTime=2026-10-26T18:05:25", b"StartTime=1793034325")
    )
