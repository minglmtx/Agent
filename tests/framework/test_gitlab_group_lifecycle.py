"""Full Group Task/Capture/Restore/Resume with file-backed native replies."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import base64
from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.sites.gitlab.tasks.group_recovery import (
    GroupRecoverySnapshot,
    GroupObserved,
    GroupRestored,
    GroupResumed,
)
from lab_generate_skill.sites.gitlab.tasks.group_resume import GroupResume
from lab_generate_skill.sites.gitlab.tasks.group_partial import GroupPartialCapture
from lab_generate_skill.sites.gitlab.tasks.group_rules import decide_group
from gitlab_group_lifecycle_fixtures import case, PROJECTS
from gitlab_group_fixtures import native_state, selected_spec, page, ORIGIN
from test_gitlab_ssh_key_inputs import reference
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_group_main_flow_capture_independent_read_full_tree_restore_once_resume(
    node_path: Path,
) -> None:
    c = case(node_path)
    task = c.task
    before = (c.state / "group.json").read_bytes()
    saved = task.execute_task(c.request, control=guard())
    assert (
        GroupRecoverySnapshot.model_validate_json(saved.private_result) == task.snapshot
    )
    prepare = c.next("prepare", "group-prepare")
    prepared = task.execute_task(prepare, control=guard())
    assert GroupObserved.model_validate_json(prepared.private_result).request == prepare
    (c.state / "group.json").write_bytes(
        native_state(inserted=True).model_dump_json().encode()
    )
    (c.state / "unrelated-file").write_bytes(b"must also be restored")
    capture = SiteCaptureRequest(
        inspection=c.next("inspect", "group-capture"),
        collector_id="gitlab-group-creation",
        collector_version="1",
    )
    observed = task.capture_task(capture, control=guard())
    assert observed.request_sha256 == capture.digest
    fact = GroupObserved.model_validate_json(observed.private_result)
    raw = c.artifacts.read(capture.inspection, fact.native, control=guard())
    independent = load_group_capture(raw, selected_spec())
    assert task.native_before is not None
    decision = decide_group(
        selected_spec(),
        task.native_before.state,
        independent.state,
        page(),
        site_origin=ORIGIN,
        selected_projects_unchanged=task.native_before.project_copy
        == independent.project_copy,
    )
    assert decision.status == "success"
    # Native replies are backed by the restored files: no SQL expectation or
    # baseline is reset to make the following restoration pass.
    restore = c.next("restore", "group-restore")
    returned = task.execute_task(restore, control=guard())
    restored = GroupRestored.model_validate_json(returned.private_result)
    assert restored.inventory == restored.snapshot.state.inventory
    assert (c.state / "group.json").read_bytes() == before
    assert (c.state / "projects.csv").read_bytes() == PROJECTS
    assert not (c.state / "unrelated-file").exists()
    resume = SiteResumeRequest(
        restore_request=restore,
        restore_result_ref=reference(
            returned.model_dump_json().encode(), content_schema="site-task-result/1"
        ),
        operation=restore.operation.cleanup(
            "group-resume", now=datetime.now(timezone.utc), seconds=20
        ),
    )
    result = GroupResume(task).resume_frontend(resume, control=guard())
    assert GroupResumed.model_validate_json(result.private_result).restored == restored
    calls = len(c.sql.calls)
    with pytest.raises(OwnershipConflict):
        GroupResume(task).resume_frontend(resume, control=guard())
    assert len(c.sql.calls) == calls and len(task.instance.generations) == 3
    task.instance.stop(guard())


@pytest.mark.parametrize("part", ["groups", "projects"])
@pytest.mark.parametrize("cancelled", [False, True])
def test_partial_capture_retains_original_error_and_never_reissues(
    node_path: Path, part: str, cancelled: bool
) -> None:
    c = case(node_path)
    error = (
        OperationStopped("CANCELLED", "original-group-read")
        if cancelled
        else OSError("original " + part + " read failed")
    )
    c.sql.error, c.sql.fail_part = error, part
    with pytest.raises(type(error)) as caught:
        c.task.execute_task(c.request, control=guard())
    assert caught.value is error and c.task.phase == "quarantined"
    result = getattr(error, "gitlab_partial_native_result")
    raw = c.artifacts.read(c.request, result, control=guard())
    partial = GroupPartialCapture.model_validate_json(raw)
    assert partial.request == c.request and partial.failed_stage == part
    assert (
        partial.retention_operation.parent_operation_id
        == c.request.operation.operation_id
    )
    assert (
        partial.retention_operation.mode == "cleanup"
        and partial.retention_operation.cancellation_ref is None
    )
    assert partial.project_copy_base64 is None and partial.qualified is False
    if part == "projects":
        assert partial.group_reply_base64 is not None
        assert (
            base64.b64decode(partial.group_reply_base64)
            == (c.state / "group.json").read_bytes()
        )
    else:
        assert partial.group_reply_base64 is None
    with pytest.raises(ValueError):
        load_group_capture(raw, selected_spec())
    calls = len(c.sql.calls)
    with pytest.raises(InvalidTransition):
        c.task.execute_task(c.request, control=guard())
    assert len(c.sql.calls) == calls and calls == (1 if part == "groups" else 2)
    c.task.instance.stop(guard())


def test_partial_retention_failure_preserves_both_errors_without_query_or_put_retry(
    node_path: Path,
) -> None:
    c = case(node_path)
    original, retention = OSError("original COPY failure"), OSError(
        "unknown diagnostic put reply"
    )
    c.sql.error, c.sql.fail_part, c.artifacts.error = original, "projects", retention
    with pytest.raises(BaseExceptionGroup) as caught:
        c.task.execute_task(c.request, control=guard())
    assert caught.value.exceptions == (original, retention)
    assert (
        c.task.phase == "quarantined"
        and len(c.sql.calls) == 2
        and len(c.artifacts.calls) == 1
    )
    with pytest.raises(InvalidTransition):
        c.task.execute_task(c.request, control=guard())
    assert len(c.sql.calls) == 2 and len(c.artifacts.calls) == 1
    c.task.instance.stop(guard())


def test_complete_publication_lost_ack_does_not_attempt_partial_publication(
    node_path: Path,
) -> None:
    c = case(node_path)
    original = OSError("unknown complete native put reply")
    c.artifacts.error = original
    with pytest.raises(OSError) as caught:
        c.task.execute_task(c.request, control=guard())
    assert (
        caught.value is original
        and len(c.sql.calls) == 2
        and len(c.artifacts.calls) == 1
    )
    assert not hasattr(original, "gitlab_partial_native_result")
    assert c.task.phase == "quarantined"
    c.task.instance.stop(guard())


def test_expired_original_control_retains_completed_group_with_independent_cleanup(
    node_path: Path,
) -> None:
    c = case(node_path)
    original = OperationStopped("CANCELLED", "original-group-capture")

    class CancelAtProjects:
        def checkpoint(self) -> float:
            if c.task.group_reader.failed_stage == "projects":
                raise original
            return 60.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(OperationStopped) as caught:
        c.task.execute_task(c.request, control=CancelAtProjects())
    assert caught.value is original and len(c.sql.calls) == 1
    result = getattr(original, "gitlab_partial_native_result")
    partial = GroupPartialCapture.model_validate_json(
        c.artifacts.read(c.request, result, control=guard())
    )
    assert (
        partial.group_reply_base64 is not None and partial.project_copy_base64 is None
    )
    assert (
        base64.b64decode(partial.group_reply_base64)
        == (c.state / "group.json").read_bytes()
    )
    assert (
        partial.retention_operation.parent_operation_id
        == c.request.operation.operation_id
    )
    assert (
        partial.retention_operation.mode == "cleanup" and c.task.phase == "quarantined"
    )
    c.task.instance.stop(guard())


@pytest.mark.parametrize(
    "change",
    [
        "binding",
        "private-input",
        "snapshot",
        "attempt",
        "parent",
        "repeat",
        "collector",
    ],
)
def test_wrong_original_identity_or_duplicate_has_no_new_read(
    node_path: Path, change: str
) -> None:
    c = case(node_path)
    c.task.execute_task(c.request, control=guard())
    request = c.next("prepare", "group-next")
    if change == "binding":
        request = request.model_copy(
            update={"binding_ref": reference(b"other", content_schema="task-binding/1")}
        )
    elif change == "private-input":
        request = request.model_copy(
            update={"private_input": request.private_input + " "}
        )
    elif change == "snapshot":
        request = request.model_copy(
            update={
                "snapshot_ref": reference(
                    b"other", content_schema="gitlab-group-recovery/1"
                )
            }
        )
    elif change == "attempt":
        request = request.model_copy(
            update={
                "operation": request.operation.model_copy(
                    update={"attempt_id": "other"}
                )
            }
        )
    elif change == "parent":
        request = c.next("restore", "group-bad-parent").model_copy(
            update={
                "operation": c.next("restore", "group-bad-parent").operation.model_copy(
                    update={"parent_operation_id": "other"}
                )
            }
        )
    elif change == "repeat":
        request = c.request
    calls = len(c.sql.calls)
    with pytest.raises((ValueError, OwnershipConflict, InvalidTransition)):
        if change == "collector":
            c.task.capture_task(
                SiteCaptureRequest(
                    inspection=c.next("inspect", "wrong-collector"),
                    collector_id="gitlab-profile-ssh-key",
                    collector_version="1",
                ),
                control=guard(),
            )
        else:
            c.task.execute_task(request, control=guard())
    assert len(c.sql.calls) == calls
    c.task.instance.stop(guard())


def test_readonly_preparation_detects_project_change_without_shifting_baseline(
    node_path: Path,
) -> None:
    c = case(node_path)
    c.task.execute_task(c.request, control=guard())
    initial = c.task.native_before
    (c.state / "projects.csv").write_bytes(b"")
    with pytest.raises(OwnershipConflict):
        c.task.execute_task(c.next("prepare", "group-drift"), control=guard())
    assert c.task.phase == "quarantined" and c.task.native_before == initial
    c.task.instance.stop(guard())


def test_owner_thread_and_cancel_before_effects_never_read_or_snapshot(
    node_path: Path,
) -> None:
    c = case(node_path)
    with ThreadPoolExecutor(max_workers=1) as executor:
        with pytest.raises(OwnershipConflict):
            executor.submit(c.task.execute_task, c.request, control=guard()).result()
    with pytest.raises(OperationStopped):
        c.task.execute_task(c.request, control=guard(-1))
    assert c.sql.calls == [] and c.task.snapshot is None and c.task.phase == "new"
    c.task.instance.stop(guard())


def test_restore_copy_failure_keeps_snapshot_and_original_error_without_retry(
    node_path: Path,
) -> None:
    c = case(node_path)
    c.task.execute_task(c.request, control=guard())
    original = c.task.snapshot
    c.commands.error = "/bin/cp"
    with pytest.raises(OSError) as caught:
        c.task.execute_task(c.next("restore", "group-failed-restore"), control=guard())
    assert (
        caught.value is c.commands.failure
        and c.task.snapshot == original
        and c.task.phase == "quarantined"
    )
    calls = len(c.commands.calls)
    with pytest.raises(InvalidTransition):
        c.task.execute_task(c.next("restore", "group-another-restore"), control=guard())
    assert len(c.commands.calls) == calls
    c.commands.error = None
    c.task.instance.stop(guard())
