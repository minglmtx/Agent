"""Actual controlled storage workers, synthetic private JSON; no GitLab service."""

from pathlib import Path
import json
import os
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.bootstrap.evidence_store import assemble_evidence_store
from lab_generate_skill.adapters.sites.native_private_evidence import (
    NativePrivateEvidence,
)
from lab_generate_skill.domain.native_private_json import (
    GITLAB_PRIVATE_JSON,
    GITLAB_GROUP_PRIVATE_JSON,
    NativePrivateJsonProfile,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from gitlab_group_fixtures import (
    selected_spec as group_spec,
    reference as group_reference,
)
from lab_generate_skill.domain.site_evidence import SitePrivateEvidencePlan
from lab_generate_skill.runtime.lifecycle import OperationGuards
from managed_store_fixtures import EngineeringAdmission
from test_gitlab_private_evidence import Case, Admission, c as c
from test_slurm_commands import Cancel, guard
from storage_installation_fixtures import storage_installation
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker


def group_request(c: Case) -> SiteTaskRequest:
    spec = group_spec()
    return SiteTaskRequest.model_validate(
        c.request.model_copy(
            update={
                "task": spec.task,
                "private_input": spec.model_dump_json(),
                "snapshot_ref": group_reference(b"{}").model_copy(
                    update={"content_schema": "gitlab-group-recovery/1"}
                ),
            }
        )
    )


def test_group_private_installed_fixture_preflight(c: Case) -> None:
    request = group_request(c)
    plan = SitePrivateEvidencePlan.model_validate(
        c.transport.plan.model_copy(update={"profile": GITLAB_GROUP_PRIVATE_JSON})
    )
    assert request.task == group_spec().task and plan.profile.family == "group_creation"
    assert request.private_input == group_spec().model_dump_json()
    assert (
        request.operation == c.request.operation
        and request.binding_ref == c.request.binding_ref
    )


def test_complete_large_private_object_uses_original_controlled_storage_workers(
    c: Case, installed_sources: InstalledFixture
) -> None:
    verify_private_storage(c, installed_sources, GITLAB_PRIVATE_JSON, c.request)


def test_group_complete_large_private_object_uses_original_controlled_storage_workers(
    c: Case, installed_sources: InstalledFixture
) -> None:
    verify_private_storage(
        c, installed_sources, GITLAB_GROUP_PRIVATE_JSON, group_request(c)
    )


def verify_private_storage(
    c: Case,
    installed_sources: InstalledFixture,
    profile: NativePrivateJsonProfile,
    request: SiteTaskRequest,
) -> None:
    config = c.transport.plan.config.model_copy(
        update={"installation": storage_installation(installed_sources)}
    )
    owner = c.transport.plan.binding.owner.model_copy(
        update={"job_id": os.environ["SLURM_JOB_ID"]}
    )
    binding = c.transport.plan.binding.model_copy(
        update={
            "owner": owner,
            "release_id": config.installation.manifest.release_id,
            "storage_config_sha256": config.sha256,
        }
    )
    plan = SitePrivateEvidencePlan(
        profile=profile,
        binding=binding,
        config=config,
        resource_journal_root=c.transport.plan.resource_journal_root,
    )
    context = c.transport.context.model_copy(
        update={"token": c.transport.context.token.model_copy(update={"owner": owner})}
    )
    storage_admission = EngineeringAdmission(binding, config)
    clock = SystemClock()
    store = assemble_evidence_store(
        binding,
        config,
        str(installed_sources.executable),
        storage_admission,
        clock,
        OperationGuards(clock, Cancel()),
        guard(60),
        max_io_seconds=60,
        cleanup_seconds=30,
    )
    initialized = store.initialize(guard(60))
    assert initialized.binding == binding
    transport = NativePrivateEvidence(
        plan, context, store, Admission(plan, context), profile=profile
    )
    size = 17_606_758
    raw = b'{"synthetic_padding":"' + b"x" * (size - 24) + b'"}'
    assert len(raw) == size
    result = transport.publish(request, raw, control=guard(60))
    published = store.last_exchange
    assert (
        published is not None
        and published.reusable
        and published.primary is None
        and published.cleanup_error is None
    )
    assert published.execution is not None and published.execution.ending is not None
    assert (
        published.execution.ending.returncode == 0
        and not published.execution.ending.kill_requested
    )
    assert transport.read(request, result, control=guard(60)) == raw
    read = store.last_exchange
    assert (
        read is not None
        and read.reusable
        and read.primary is None
        and read.cleanup_error is None
    )
    assert read.execution is not None and read.execution.ending is not None
    assert (
        read.execution.ending.returncode == 0
        and not read.execution.ending.kill_requested
    )
    assert published.execution.ending.process_id != read.execution.ending.process_id
    assert store.state == "ready" and not transport.quarantined
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / (
        profile.family + "-private-controlled-storage.json"
    )
    output.write_text(
        json.dumps(
            {
                "engineering_only": True,
                "profile": profile.model_dump(mode="json"),
                "request": request.model_dump(mode="json"),
                "actual_storage_workers": True,
                "native_site_worker_guard": False,
                "gitlab_db_started": False,
                "actor_calls": 0,
                "paid_calls": 0,
                "synthetic_payload": True,
                "complete_bytes": len(raw),
                "reference": result.payload_ref.model_dump(mode="json"),
                "site_wire_limit_unchanged": True,
                "task_result_limit_unchanged": True,
                "put_end": published.execution.ending.model_dump(mode="json"),
                "read_end": read.execution.ending.model_dump(mode="json"),
                "storage_config_sha256": config.sha256,
                "run_storage_without_source_claim": binding.source_task_id is None,
            },
            indent=2,
        )
        + "\n"
    )
