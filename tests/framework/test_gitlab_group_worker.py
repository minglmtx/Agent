"""Actual fixed family assembly/dispatch with explicit simulated native services."""

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_group_lifecycle import build_group_lifecycle
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceContext
from lab_generate_skill.domain.site_worker import (
    SiteInstanceStarted,
    SiteWorkerConfiguration,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.worker_instance import GitlabWorkerInstance
from lab_generate_skill.sites.gitlab.tasks.group_lifecycle import GroupLifecycle
from lab_generate_skill.sites.gitlab.tasks.group_recovery import (
    GroupObserved,
    GroupRecoverySnapshot,
    GroupRestored,
    GroupResumed,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from generator_worker_fixtures import unit_guard
from gitlab_group_lifecycle_fixtures import SqlReplies, PROJECTS
from gitlab_group_fixtures import selected_spec, native_state
from gitlab_ssh_lifecycle_fixtures import Artifacts
from gitlab_site_storage_live import missing_asset_configuration
from storage_installation_fixtures import storage_installation
from test_gitlab_instance import instance
from test_gitlab_ssh_key_inputs import reference
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_declared_group_worker_dispatches_original_task_capture_restore_resume(
    node_path: Path,
) -> None:
    site, _, groups, _ = instance(node_path)
    cfg = missing_asset_configuration(
        storage_installation(),
        job_id="4752096",
        root=node_path / "storage",
        parent=node_path,
    )
    assert cfg.private_evidence is not None
    cfg = SiteWorkerConfiguration.model_validate(
        {
            **cfg.model_dump(),
            "private_evidence": cfg.private_evidence.model_copy(
                update={"profile": GITLAB_GROUP_PRIVATE_JSON}
            ),
        }
    )
    site.files_plan = cfg.files
    initial = SiteInstanceStarted(
        files=cfg.files, endpoint="http://127.0.0.1:12001/", ports=(12001, 12002)
    )
    context = SitePrivateEvidenceContext(
        configuration_sha256=hashlib.sha256(cfg.model_dump_json().encode()).hexdigest(),
        token=cfg.token,
        instance=initial,
        owner_guard=unit_guard(current_process_identity(), guard()),
    )
    state = Path(cfg.files.state_root)

    class StartedArtifacts(Artifacts):
        def bind_instance(
            self, started: SiteInstanceStarted, control: OperationControl
        ) -> None:
            super().bind_instance(started, control)
            assert started == initial
            (state / "group.json").write_bytes(
                native_state().model_dump_json().encode()
            )
            (state / "projects.csv").write_bytes(PROJECTS)

    artifacts = StartedArtifacts(
        node_path / "evidence", context, profile=GITLAB_GROUP_PRIVATE_JSON
    )
    sql = SqlReplies(state)
    worker = GitlabWorkerInstance(
        cfg,
        site,
        artifacts,
        sql,
        lambda control: "native-user",
        group_lifecycle_factory=build_group_lifecycle,
    )
    op = OperationContext(
        operation_id="group-snapshot",
        run_id=cfg.token.owner.run_id,
        owner_id=cfg.token.owner.owner_id,
        attempt_id="attempt",
        allocation_id=cfg.token.allocation_id,
        recovery_ref=reference(b"{}", content_schema="recovery-plan/1"),
        deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
    )
    request = SiteTaskRequest(
        task=selected_spec().task,
        binding_ref=reference(b"{}", content_schema="task-binding/1"),
        operation=op,
        action="snapshot",
        private_input=selected_spec().model_dump_json(),
    )
    with pytest.raises(InvalidTransition):
        worker.execute_task(request, control=guard())
    assert not sql.calls and not Path(cfg.files.node_root).exists()
    assert worker.start(guard()) == initial and isinstance(worker.tasks, GroupLifecycle)
    snapshot = worker.execute_task(request, control=guard())
    saved = GroupRecoverySnapshot.model_validate_json(snapshot.private_result)
    ref = reference(
        snapshot.private_result.encode(), content_schema=saved.schema_version
    )

    def next_request(action: str, name: str) -> SiteTaskRequest:
        # Only the test input construction is dynamic; dispatch uses fixed code.
        return SiteTaskRequest.model_validate(
            {
                **request.model_dump(),
                "action": action,
                "snapshot_ref": ref,
                "operation": op.model_copy(
                    update={
                        "operation_id": name,
                        "mode": "cleanup" if action == "restore" else "execute",
                        "parent_operation_id": (
                            "group-prepare" if action == "restore" else None
                        ),
                    }
                ),
            }
        )

    prepared = worker.execute_task(
        next_request("prepare", "group-prepare"), control=guard()
    )
    assert GroupObserved.model_validate_json(prepared.private_result).snapshot == saved
    capture = SiteCaptureRequest(
        inspection=next_request("inspect", "group-capture"),
        collector_id="gitlab-group-creation",
        collector_version="1",
    )
    returned = worker.capture_task(capture, control=guard())
    assert returned.request_sha256 == capture.digest
    wrong = request.model_copy(
        update={"task": request.task.model_copy(update={"family": "profile_ssh_key"})}
    )
    calls = len(sql.calls)
    with pytest.raises(OwnershipConflict, match="declared family"):
        worker.execute_task(wrong, control=guard())
    assert len(sql.calls) == calls
    restore = next_request("restore", "group-restore")
    restored = worker.execute_task(restore, control=guard())
    assert GroupRestored.model_validate_json(restored.private_result).snapshot == saved
    resume = SiteResumeRequest(
        restore_request=restore,
        restore_result_ref=reference(
            restored.model_dump_json().encode(), content_schema="site-task-result/1"
        ),
        operation=restore.operation.cleanup(
            "group-resume", now=datetime.now(timezone.utc), seconds=20
        ),
    )
    # Task recovery and environment recovery are distinct original identities.
    # An incorrect environment reference must fail before consuming resume.
    calls = len(sql.calls)
    with pytest.raises(OwnershipConflict, match="environment recovery"):
        worker.resume_frontend(resume, control=guard())
    assert len(sql.calls) == calls and worker.resumption is None
    resume = SiteResumeRequest.model_validate(
        resume.model_copy(
            update={
                "operation": resume.operation.model_copy(
                    update={"recovery_ref": cfg.token.recovery_ref}
                )
            }
        )
    )
    resumed = worker.resume_frontend(resume, control=guard())
    assert (
        GroupResumed.model_validate_json(resumed.private_result).restored.request
        == restore
    )
    with pytest.raises(InvalidTransition):
        worker.resume_frontend(resume, control=guard())
    assert len(sql.calls) == 10 and len(site.generations) == 3
    worker.stop(guard())
    assert all(group.stopped for group in groups)
