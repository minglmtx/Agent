"""Selected task/Capture/Restore/Resume, including wrong scope and unknowns."""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.sites.gitlab.tasks.ssh_key_recovery import (
    SshKeyRecoverySnapshot,
    SshKeyObserved,
    SshKeyRestored,
    SshKeyResumed,
)
from lab_generate_skill.sites.gitlab.tasks.ssh_key_resume import SshKeyResume
from gitlab_ssh_lifecycle_fixtures import case
from gitlab_ssh_state_fixtures import native_state
from test_gitlab_ssh_key_inputs import reference
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_original_task_preparation_capture_full_restore_and_once_resume(
    node_path: Path,
) -> None:
    c = case(node_path)
    task = c.task
    snapshot = task.execute_task(c.request, control=guard())
    assert (
        SshKeyRecoverySnapshot.model_validate_json(snapshot.private_result)
        == task.snapshot
    )
    assert task.snapshot is not None
    with pytest.raises(InvalidTransition):
        task.execute_task(c.request, control=guard())
    prepare = c.next("prepare", "ssh-prepare")
    prepared = task.execute_task(prepare, control=guard())
    assert (
        SshKeyObserved.model_validate_json(prepared.private_result).request == prepare
    )
    c.reader.value = native_state(inserted=True)
    capture = SiteCaptureRequest(
        inspection=c.next("inspect", "ssh-capture"),
        collector_id="gitlab-profile-ssh-key",
        collector_version="1",
    )
    observed = task.capture_task(capture, control=guard())
    assert observed.request_sha256 == capture.digest
    fact = SshKeyObserved.model_validate_json(observed.private_result)
    assert fact.native.request_sha256 == capture.inspection.digest
    with pytest.raises(InvalidTransition):
        task.capture_task(capture, control=guard())
    c.reader.value = native_state()
    restore = c.next("restore", "ssh-restore")
    returned = task.execute_task(restore, control=guard())
    assert (
        SshKeyRestored.model_validate_json(returned.private_result).inventory
        == task.snapshot.state.inventory
    )
    resume = SiteResumeRequest(
        restore_request=restore,
        restore_result_ref=reference(
            returned.model_dump_json().encode(), content_schema="site-task-result/1"
        ),
        operation=restore.operation.cleanup(
            "ssh-resume", now=datetime.now(timezone.utc), seconds=20
        ),
    )
    runner = SshKeyResume(task)
    resumed = runner.resume_frontend(resume, control=guard())
    assert (
        SshKeyResumed.model_validate_json(resumed.private_result).restored.request
        == restore
    )
    assert len(task.instance.generations) == 3
    with pytest.raises(OwnershipConflict):
        runner.resume_frontend(resume, control=guard())
    task.instance.stop(guard())


@pytest.mark.parametrize(
    "change", ["binding", "private_input", "snapshot", "attempt", "operation", "phase"]
)
def test_wrong_scope_or_repeat_rejected_before_new_native_effect(
    node_path: Path, change: str
) -> None:
    c = case(node_path)
    c.task.execute_task(c.request, control=guard())
    request = c.next("prepare", "next")
    if change == "binding":
        request = request.model_copy(
            update={
                "binding_ref": reference(b"foreign", content_schema="task-binding/1")
            }
        )
    elif change == "private_input":
        request = request.model_copy(
            update={"private_input": " " + request.private_input}
        )
    elif change == "snapshot":
        request = request.model_copy(
            update={
                "snapshot_ref": reference(
                    b"wrong", content_schema="gitlab-ssh-key-recovery/1"
                )
            }
        )
    elif change == "attempt":
        request = request.model_copy(
            update={
                "operation": request.operation.model_copy(
                    update={"attempt_id": "foreign"}
                )
            }
        )
    elif change == "operation":
        request = request.model_copy(update={"operation": c.request.operation})
    else:
        request = c.next("inspect", "too-early")
    before = (c.reader.calls, len(c.artifacts.calls))
    with pytest.raises((OwnershipConflict, InvalidTransition)):
        c.task.execute_task(request, control=guard())
    assert before == (c.reader.calls, len(c.artifacts.calls))
    c.task.instance.stop(guard())


@pytest.mark.parametrize(
    "phase",
    [
        "snapshot_read",
        "publication",
        "prepare_read",
        "prepare_changed",
        "restore_changed",
    ],
)
def test_failure_preserves_snapshot_and_quarantines_without_replay(
    node_path: Path, phase: str
) -> None:
    c = case(node_path)
    error = OperationStopped("CANCELLED", "original-native-read")
    request = c.request
    if phase in ("prepare_read", "prepare_changed", "restore_changed"):
        c.task.execute_task(c.request, control=guard())
        request = c.next(
            "restore" if phase == "restore_changed" else "prepare", "failing"
        )
    if phase in ("snapshot_read", "prepare_read"):
        c.reader.error = error
    elif phase == "publication":
        c.artifacts.error = OSError("private CAS confirmation lost")
    else:
        c.reader.value = native_state(inserted=True)
    with pytest.raises((OperationStopped, OSError, OwnershipConflict)) as caught:
        c.task.execute_task(request, control=guard())
    if phase in ("snapshot_read", "prepare_read"):
        assert caught.value is error
    assert c.task.phase == "quarantined" and not c.task.busy
    before = (c.reader.calls, len(c.artifacts.calls), len(c.task.instance.generations))
    with pytest.raises(InvalidTransition):
        c.task.execute_task(request, control=guard())
    assert before == (
        c.reader.calls,
        len(c.artifacts.calls),
        len(c.task.instance.generations),
    )
    c.task.instance.stop(guard())
