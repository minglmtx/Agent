"""Current Task/Capture/stopped restore/Resume composition, no real Postmill."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
    EvidenceIntegrityError,
)
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.sites.reddit.native_schema import NativeCapture
from lab_generate_skill.sites.reddit.tasks.image_recovery import (
    ImageRecoverySnapshot,
    ImageObserved,
    ImageRestored,
    ImageResumed,
)
from lab_generate_skill.sites.reddit.tasks.image_resume import ImageResume
from reddit_image_lifecycle_fixtures import case, Case
from reddit_image_state_fixtures import posted_data
from test_gitlab_ssh_key_inputs import reference
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


def restore_request(c: Case) -> SiteResumeRequest:
    restore = c.next("restore", "image-restore")
    returned = c.task.execute_task(restore, control=guard())
    return SiteResumeRequest(
        restore_request=restore,
        restore_result_ref=reference(
            returned.model_dump_json().encode(), content_schema="site-task-result/1"
        ),
        operation=restore.operation.cleanup(
            "image-resume", now=datetime.now(timezone.utc), seconds=20
        ),
    )


def test_original_prepare_capture_stopped_restore_verified_resume(
    node_path: Path,
) -> None:
    c = case(node_path)
    task = c.task
    saved = task.execute_task(c.request, control=guard())
    assert (
        ImageRecoverySnapshot.model_validate_json(saved.private_result) == task.snapshot
    )
    assert task.snapshot is not None and task.baseline_ids is not None
    baseline_path = (
        Path(task.instance.spec.native_input_root) / task.baseline_ids.filename
        if task.instance.spec
        else None
    )
    assert baseline_path is not None and baseline_path.is_file()
    assert task.snapshot.native_before.payload_ref.size_bytes > 0
    with pytest.raises(InvalidTransition):
        task.execute_task(c.request, control=guard())
    prepare = c.next("prepare", "image-prepare")
    result = task.execute_task(prepare, control=guard())
    prepared = ImageObserved.model_validate_json(result.private_result)
    assert prepared.request == prepare
    c.reader.value = NativeCapture.model_validate_json(json.dumps(posted_data()))
    capture = SiteCaptureRequest(
        inspection=c.next("inspect", "image-capture"),
        collector_id="reddit-native-image",
        collector_version="1",
    )
    result = task.capture_task(capture, control=guard())
    observed = ImageObserved.model_validate_json(result.private_result)
    assert result.request_sha256 == capture.digest
    raw = c.artifacts.read(capture.inspection, observed.native, control=guard())
    assert NativeCapture.model_validate_json(raw) == c.reader.value
    calls = c.reader.calls
    resume = restore_request(c)
    assert c.reader.calls == calls  # no database reads while PostgreSQL is stopped
    assert task.restore_result is not None
    restored = ImageRestored.model_validate_json(task.restore_result.private_result)
    assert restored.inventory == task.snapshot.state.inventory
    assert task.instance.state == "restored" and len(task.instance.generations) == 2
    assert baseline_path.is_file()  # immutable input is outside the mutable state tree
    c.reader.value = c.reader.initial.capture
    runner = ImageResume(task)
    resumed = runner.resume_frontend(resume, control=guard())
    assert ImageResumed.model_validate_json(resumed.private_result).restored == restored
    assert task.phase == "resumed" and len(task.instance.generations) == 3
    with pytest.raises(OwnershipConflict):
        runner.resume_frontend(resume, control=guard())
    with pytest.raises(OwnershipConflict):
        ImageResume(task).resume_frontend(resume, control=guard())
    task.instance.stop(guard())


@pytest.mark.parametrize(
    "change",
    [
        "binding",
        "private_input",
        "snapshot",
        "attempt",
        "operation",
        "phase",
        "parent",
        "collector",
        "thread",
    ],
)
def test_bad_scope_or_repeat_before_native_effect(node_path: Path, change: str) -> None:
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
                    b"wrong", content_schema="reddit-image-recovery/2"
                )
            }
        )
    elif change in ("attempt", "parent"):
        if change == "parent":
            request = c.next("restore", "wrong-parent")
        key = "attempt_id" if change == "attempt" else "parent_operation_id"
        request = request.model_copy(
            update={"operation": request.operation.model_copy(update={key: "foreign"})}
        )
    elif change == "operation":
        request = request.model_copy(update={"operation": c.request.operation})
    elif change == "phase":
        request = c.next("inspect", "too-early")
    before = (c.reader.calls, len(c.artifacts.calls), len(c.task.instance.generations))
    with pytest.raises((OwnershipConflict, InvalidTransition, ValueError)):
        if change == "collector":
            c.task.capture_task(
                SiteCaptureRequest(
                    inspection=c.next("inspect", "capture"),
                    collector_id="gitlab-profile-ssh-key",
                    collector_version="1",
                ),
                control=guard(),
            )
        elif change == "thread":
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(c.task.execute_task, request, control=guard()).result()
        else:
            c.task.execute_task(request, control=guard())
    assert before == (
        c.reader.calls,
        len(c.artifacts.calls),
        len(c.task.instance.generations),
    )
    c.task.instance.stop(guard())


@pytest.mark.parametrize(
    "private_input", ["", "null", "[]", "{}", "false", "1", '"text"']
)
def test_empty_wrong_type_or_incomplete_input_before_effect(
    node_path: Path, private_input: str
) -> None:
    c = case(node_path)
    with pytest.raises((ValidationError, OwnershipConflict)):
        invalid = c.request.model_copy(update={"private_input": private_input})
        c.task.execute_task(invalid, control=guard())
    assert not c.reader.calls and not c.artifacts.calls and c.task.phase == "new"
    c.task.instance.stop(guard())


@pytest.mark.parametrize(
    "failure",
    [
        "read",
        "publication",
        "prepare-read",
        "prepare-changed",
        "baseline-tampered",
        "restore",
        "resume-read",
        "resume-changed",
    ],
)
def test_partial_failure_keeps_original_facts_and_never_repeats(
    node_path: Path, failure: str
) -> None:
    c = case(node_path)
    request = c.request
    if failure not in ("read", "publication"):
        c.task.execute_task(c.request, control=guard())
        request = c.next("prepare", "preparing")
    runner = None
    resume = None
    if failure.startswith("resume"):
        resume = restore_request(c)
        runner = ImageResume(c.task)
    error = OperationStopped("CANCELLED", "original-native-read")
    if failure in ("read", "prepare-read", "resume-read"):
        c.reader.error = error
    elif failure == "publication":
        c.artifacts.error = OSError("private CAS confirmation lost")
    elif failure.endswith("changed"):
        c.reader.value = NativeCapture.model_validate_json(json.dumps(posted_data()))
    elif failure == "baseline-tampered":
        assert c.task.baseline_ids is not None and c.task.instance.spec is not None
        path = (
            Path(c.task.instance.spec.native_input_root) / c.task.baseline_ids.filename
        )
        path.chmod(0o600)
    elif failure == "restore":
        request = c.next("restore", "restoring")
        from reddit_snapshot_fixtures import TreeCommands

        assert isinstance(c.task.instance.commands, TreeCommands)
        c.task.instance.commands.error = "/bin/cp"
    with pytest.raises(
        (
            OperationStopped,
            OSError,
            ValueError,
            OwnershipConflict,
            EvidenceIntegrityError,
        )
    ) as caught:
        if runner is not None and resume is not None:
            runner.resume_frontend(resume, control=guard())
        else:
            c.task.execute_task(request, control=guard())
    assert c.task.phase == "quarantined" and not c.task.busy
    assert hasattr(caught.value, "reddit_native_result")
    if failure not in ("read", "publication"):
        assert getattr(caught.value, "reddit_recovery_snapshot") == c.task.snapshot
    before = (c.reader.calls, len(c.artifacts.calls), len(c.task.instance.generations))
    with pytest.raises((InvalidTransition, OwnershipConflict)):
        if resume is not None:
            ImageResume(c.task).resume_frontend(resume, control=guard())
        else:
            c.task.execute_task(request, control=guard())
    assert before == (
        c.reader.calls,
        len(c.artifacts.calls),
        len(c.task.instance.generations),
    )
    c.task.instance.stop(guard())


@pytest.mark.parametrize(
    "change", ["restore-bytes", "restore-request", "operation-reused"]
)
def test_resume_wrong_identity_before_restart(node_path: Path, change: str) -> None:
    c = case(node_path)
    c.task.execute_task(c.request, control=guard())
    request = restore_request(c)
    if change == "restore-bytes":
        request = request.model_copy(
            update={
                "restore_result_ref": reference(
                    b"wrong", content_schema="site-task-result/1"
                )
            }
        )
    elif change == "restore-request":
        request = request.model_copy(
            update={
                "restore_request": request.restore_request.model_copy(
                    update={
                        "binding_ref": reference(
                            b"wrong", content_schema="task-binding/1"
                        )
                    }
                )
            }
        )
    else:
        request = request.model_copy(
            update={
                "operation": request.operation.model_copy(
                    update={"operation_id": c.request.operation.operation_id}
                )
            }
        )
    before = c.reader.calls, len(c.task.instance.generations)
    with pytest.raises(OwnershipConflict):
        ImageResume(c.task).resume_frontend(request, control=guard())
    assert before == (c.reader.calls, len(c.task.instance.generations))
    c.task.instance.stop(guard())


@pytest.mark.parametrize("stage", ["snapshot", "prepare", "restore", "resume"])
def test_late_cancel_retains_known_result_and_forbids_replay(
    node_path: Path, stage: str
) -> None:
    c = case(node_path)
    task = c.task
    request = c.request
    resume = None
    runner = ImageResume(task)
    if stage != "snapshot":
        task.execute_task(request, control=guard())
        request = c.next("prepare" if stage == "prepare" else "restore", "next")
        if stage == "resume":
            resume = restore_request(c)
    original = OperationStopped("CANCELLED", "late-result")

    original_control = guard()

    class Late:
        def checkpoint(self) -> float:
            known = runner.result if stage == "resume" else task.last_result
            if known is not None and (
                stage == "resume" or known.request_sha256 == request.digest
            ):
                raise original
            return original_control.checkpoint()

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(OperationStopped) as caught:
        if resume is not None:
            runner.resume_frontend(resume, control=Late())
        else:
            task.execute_task(request, control=Late())
    assert caught.value is original and task.phase == "quarantined"
    name = "reddit_resume_result" if stage == "resume" else "reddit_task_result"
    assert getattr(original, name) is not None
    before = c.reader.calls, len(task.instance.generations)
    with pytest.raises((InvalidTransition, OwnershipConflict)):
        if resume is not None:
            ImageResume(task).resume_frontend(resume, control=guard())
        else:
            task.execute_task(request, control=guard())
    assert before == (c.reader.calls, len(task.instance.generations))
    task.instance.stop(guard())
