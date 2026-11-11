"""Held-inode removal proof; pathname absence or unrelated errno never suffices."""

import errno
import os
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.adapters.slurm import cgroup_pin as module
from lab_generate_skill.adapters.slurm.kernel_capture import KernelCapture
from lab_generate_skill.adapters.slurm.kernel_files import KernelControl
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.slurm_quiescence import SlurmUserRemoval
from cgroup_fixtures import Control
from step_kernel_fixtures import StepKernel, step_kernel as step_kernel
from test_linux_cgroups import kernel as kernel


@pytest.fixture
def pinned(step_kernel: StepKernel, monkeypatch: pytest.MonkeyPatch) -> Any:
    original = step_kernel.observe()
    step_kernel.exit()
    directory = KernelControl(
        original.user_path, original.device, original.user_inode, 0, 0, 0o40755, False
    )
    events = replace(
        directory,
        path=directory.path + "/cgroup.events",
        inode=directory.inode + 10,
        mode=0o100444,
    )
    values = {
        fd: SimpleNamespace(
            st_dev=c.device, st_ino=c.inode, st_uid=0, st_gid=0, st_mode=c.mode
        )
        for fd, c in ((100, directory), (101, events))
    }
    links = {100: directory.path + " (deleted)", 101: events.path + " (deleted)"}
    state: dict[str, Any] = {"errno": errno.ENODEV, "closed": []}

    def read(fd: int, limit: int) -> bytes:
        if state["errno"] is not None:
            raise OSError(state["errno"], "events")
        return b"populated 0\nfrozen 0\n"

    fake_os = SimpleNamespace(
        getpid=os.getpid,
        makedev=os.makedev,
        fstat=lambda fd: values[fd],
        readlink=lambda path: links[int(path.rsplit("/", 1)[1])],
        lseek=lambda *args: None,
        read=read,
        SEEK_SET=os.SEEK_SET,
    )
    monkeypatch.setattr(module, "os", fake_os)
    handle = module.PinnedUserTree(
        original, (100, 101), KernelCapture((), (directory, events)), directory, events
    )
    return handle, state, values, links


@pytest.mark.parametrize("event_suffix", ["", " (deleted)"])
def test_positive_removed_original_repeat(pinned: Any, event_suffix: str) -> None:
    handle, _, _, links = pinned
    links[101] = handle.original.user_path + "/cgroup.events" + event_suffix
    first = handle.removed_observation(Control())
    assert first == handle.removed_observation(Control())
    assert isinstance(first.facts, SlurmUserRemoval)
    assert (
        first.facts.original == handle.original
        and first.facts.writer_status == "missing"
    )
    assert len(first.capture.pinned_controls) == 2
    assert all(p.events_errno == errno.ENODEV for p in first.capture.pinned_controls)


@pytest.mark.parametrize(
    "number", [None, errno.ENOENT, errno.EIO, errno.EBADF, errno.EACCES]
)
def test_other_event_results_cannot_prove_removal(
    pinned: Any, number: int | None
) -> None:
    handle, state, _, _ = pinned
    state["errno"] = number
    with pytest.raises(OwnershipConflict) as caught:
        handle.removed_observation(Control())
    assert (
        getattr(caught.value, "slurm_kernel_capture").pinned_controls[0].events_errno
        == number
    )


@pytest.mark.parametrize("fd", [100, 101])
@pytest.mark.parametrize("field", ["st_dev", "st_ino", "st_uid", "st_gid", "st_mode"])
def test_descriptor_drift_rejected(pinned: Any, fd: int, field: str) -> None:
    handle, _, values, _ = pinned
    setattr(values[fd], field, getattr(values[fd], field) + 1)
    with pytest.raises(OwnershipConflict, match="identity changed"):
        handle.removed_observation(Control())


@pytest.mark.parametrize(
    "fd,value", [(100, "live"), (100, "foreign"), (101, "foreign")]
)
def test_deleted_link_must_be_original(pinned: Any, fd: int, value: str) -> None:
    handle, _, _, links = pinned
    links[fd] = (
        links[fd].replace(" (deleted)", "") if value == "live" else "/other (deleted)"
    )
    with pytest.raises(OwnershipConflict):
        handle.removed_observation(Control())


def test_missing_path_needs_positive_pin_evidence(
    pinned: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle, state, _, _ = pinned
    missing = FileNotFoundError(errno.ENOENT, "removed")
    partial = KernelCapture((), (), handle.original.user_path)
    setattr(missing, "slurm_kernel_capture", partial)

    def fail(*args: Any) -> Any:
        raise missing

    monkeypatch.setattr(module, "observe_user_quiescence", fail)
    observed = handle.observe(Control())
    assert isinstance(observed.facts, SlurmUserRemoval)
    assert observed.capture.failed_control_path == handle.original.user_path
    state["errno"] = None
    with pytest.raises(BaseExceptionGroup) as caught:
        handle.observe(Control())
    assert caught.value.exceptions[0] is missing
    assert isinstance(caught.value.exceptions[1], OwnershipConflict)


@pytest.mark.parametrize(
    "failure",
    [
        PermissionError(errno.EACCES, "denied"),
        OSError(errno.EIO, "read"),
        ValueError("changed"),
        BaseExceptionGroup(
            "read and close",
            [FileNotFoundError(errno.ENOENT, "missing"), OSError("close")],
        ),
    ],
)
def test_unrelated_errors_never_use_alternate_observation(
    pinned: Any, monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    handle, _, _, _ = pinned

    def fail(*args: Any) -> Any:
        raise failure

    monkeypatch.setattr(module, "observe_user_quiescence", fail)
    monkeypatch.setattr(
        handle, "removed_observation", lambda *args: pytest.fail("masked error")
    )
    with pytest.raises(BaseException) as caught:
        handle.observe(Control())
    assert caught.value is failure


def test_foreign_closed_and_close_failure_no_fd_retry(
    pinned: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle, _, _, _ = pinned
    original_context = handle._context
    handle._context = (-1, -1)
    with pytest.raises(OwnershipConflict):
        handle.observe(Control())
    with pytest.raises(OwnershipConflict):
        handle.close()
    handle._context = original_context
    calls = []
    failure = OSError("close")

    def fail(fds: tuple[int, ...], primary: BaseException | None) -> None:
        calls.append(fds)
        raise failure

    monkeypatch.setattr(module, "close_all", fail)
    with pytest.raises(OSError) as caught:
        handle.close()
    assert caught.value is failure and calls == [(101, 100)]
    handle.close()
    assert len(calls) == 1
    with pytest.raises(OwnershipConflict):
        handle.observe(Control())


@pytest.mark.parametrize("kind", ["writer", "mount"])
def test_removed_handles_do_not_override_live_writer_or_wrong_mount(
    pinned: Any, step_kernel: StepKernel, kind: str
) -> None:
    from step_kernel_fixtures import WORKER_PID, WORKER_STAT

    handle, _, _, _ = pinned
    if kind == "writer":
        step_kernel.values[f"/proc/{WORKER_PID}/stat"] = WORKER_STAT
    else:
        handle.original = handle.original.model_copy(
            update={"mount_id": handle.original.mount_id + 1}
        )
    with pytest.raises((OwnershipConflict, ValueError)):
        handle.removed_observation(Control())


def test_new_closure_contract_rejects_old_schema(pinned: Any) -> None:
    from pydantic import ValidationError
    from lab_generate_skill.domain.generator_step import GeneratorStepClosed
    from slurm_step_fixtures import target, token

    handle, _, _, _ = pinned
    original = target()
    # The synthetic pinned fixture uses a different execution. Construct the
    # closure against its own original tree and an observer on that same host.
    removal = handle.removed_observation(Control()).facts
    adapted = original.model_copy(
        update={
            "execution": original.execution.model_copy(
                update={
                    "job_id": handle.original.job_id,
                    "raw_job_id": handle.original.job_id,
                    "uid": handle.original.uid,
                }
            ),
            "launcher": removal.observer,
            "worker": handle.original,
        }
    )
    ref = token().recovery_ref.model_copy(
        update={"content_schema": "generator-step-raw/1"}
    )
    closed = GeneratorStepClosed(target=adapted, quiescence=removal, evidence=ref)
    assert GeneratorStepClosed.model_validate_json(closed.model_dump_json()) == closed
    with pytest.raises(ValidationError):
        GeneratorStepClosed.model_validate(
            closed.model_copy(update={"schema_version": "generator-step-closed/1"})
        )
