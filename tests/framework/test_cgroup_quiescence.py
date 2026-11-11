"""Original numeric user subtree: no missing-path, reused-PID or failure shortcuts."""

from dataclasses import replace
import errno
from pathlib import Path
from typing import Any

import pytest

from lab_generate_skill.adapters.slurm import kernel_capture as captures
from lab_generate_skill.adapters.slurm.cgroup_quiescence import observe_user_quiescence
from lab_generate_skill.adapters.slurm.kernel_files import KernelRead, KernelControl
from lab_generate_skill.domain.slurm_quiescence import SlurmUserQuiescence
from cgroup_fixtures import PID, MOUNT, Control, writer
from step_kernel_fixtures import (
    STEP_USER,
    WORKER_PID,
    WORKER_STAT,
    StepKernel,
    step_kernel as step_kernel,
)
from test_linux_cgroups import kernel as kernel


def test_original_exit_repeat_and_pid_reuse(step_kernel: StepKernel) -> None:
    original = step_kernel.observe()
    step_kernel.exit()
    first = observe_user_quiescence(original, Control())
    again = observe_user_quiescence(original, Control())
    assert first == again
    assert first.facts.original == original
    assert first.facts.observer == writer()
    assert first.facts.writer_status == "missing"
    assert first.facts.replacement_start_ticks is None
    assert (
        SlurmUserQuiescence.model_validate_json(first.facts.model_dump_json())
        == first.facts
    )
    step_kernel.values[f"/proc/{WORKER_PID}/stat"] = WORKER_STAT.replace(
        b" 42 ", b" 43 "
    )
    reused = observe_user_quiescence(original, Control())
    assert reused.facts.writer_status == "reused"
    assert reused.facts.replacement_start_ticks == 43


@pytest.mark.parametrize("state", [b"S", b"R", b"Z"])
def test_original_incarnation_even_zombie_rejected(
    step_kernel: StepKernel, state: bytes
) -> None:
    original = step_kernel.observe()
    step_kernel.exit()
    step_kernel.values[f"/proc/{WORKER_PID}/stat"] = WORKER_STAT.replace(
        b") S ", b") " + state + b" "
    )
    with pytest.raises(ValueError, match="still exists"):
        observe_user_quiescence(original, Control())


@pytest.mark.parametrize(
    "suffix,value",
    [
        ("cgroup.events", b"populated 1\nfrozen 0\n"),
        ("cgroup.events", b"populated 0\nfrozen 1\n"),
        ("cgroup.events", b""),
        ("cgroup.events", b"populated 0\nfrozen 0\nextra 0\n"),
        ("cgroup.events", b"populated 0\npopulated 0\nfrozen 0\n"),
        ("cgroup.events", b"populated false\nfrozen 0\n"),
        ("cgroup.type", b"domain threaded\n"),
        ("cgroup.procs", b"999\n"),
        ("cgroup.threads", b"999\n"),
        ("cgroup.procs", b"\n"),
    ],
)
def test_nonempty_frozen_or_unknown_layout(
    step_kernel: StepKernel, suffix: str, value: bytes
) -> None:
    original = step_kernel.observe()
    step_kernel.exit()
    step_kernel.values[STEP_USER + "/" + suffix] = value
    with pytest.raises(ValueError) as caught:
        observe_user_quiescence(original, Control())
    assert any(
        r.content == value for r in getattr(caught.value, "slurm_kernel_capture").reads
    )


@pytest.mark.parametrize(
    "field,value",
    [("mount_id", 139), ("device", 27), ("user_inode", 99999), ("uid", 1001)],
)
def test_wrong_original_subtree(
    step_kernel: StepKernel, field: str, value: int
) -> None:
    original = step_kernel.observe().model_copy(update={field: value})
    step_kernel.exit()
    with pytest.raises(ValueError):
        observe_user_quiescence(original, Control())


@pytest.mark.parametrize(
    "field,value",
    [("node_id", "other"), ("boot_id", "00000000-0000-0000-0000-000000000000")],
)
def test_wrong_host_boot(step_kernel: StepKernel, field: str, value: str) -> None:
    original = step_kernel.observe()
    original = original.model_copy(
        update={"writer": original.writer.model_copy(update={field: value})}
    )
    step_kernel.exit()
    with pytest.raises(ValueError, match="same host boot"):
        observe_user_quiescence(original, Control())


@pytest.mark.parametrize(
    "target", [STEP_USER, STEP_USER + "/cgroup.procs", "/sys/fs/cgroup/cgroup.threads"]
)
@pytest.mark.parametrize("mode", ["missing", "changed", "permission"])
def test_control_path_failure(
    step_kernel: StepKernel, monkeypatch: pytest.MonkeyPatch, target: str, mode: str
) -> None:
    original = step_kernel.observe()
    step_kernel.exit()
    inspect = getattr(captures, "inspect_control")
    calls = 0

    def checked(path: Path, control: Any, *, directory: bool) -> KernelControl:
        nonlocal calls
        result: KernelControl = inspect(path, control, directory=directory)
        if str(path) == target:
            calls += 1
            if mode == "missing":
                raise FileNotFoundError(
                    errno.ENOENT, "Original control absent", str(path)
                )
            if mode == "permission":
                raise PermissionError(errno.EACCES, "Denied", str(path))
            if calls == 2:
                return replace(result, inode=result.inode + 10000)
        return result

    monkeypatch.setattr(captures, "inspect_control", checked)
    with pytest.raises((ValueError, OSError)) as caught:
        observe_user_quiescence(original, Control())
    capture = getattr(caught.value, "slurm_kernel_capture")
    if mode != "changed":
        assert capture.failed_control_path == target


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("no errno is not confirmed absence"),
        PermissionError(errno.EACCES, "denied"),
        OSError(errno.EIO, "read failure"),
        BaseExceptionGroup(
            "read and close",
            [
                FileNotFoundError(errno.ENOENT, "missing"),
                OSError(errno.EIO, "close failed"),
            ],
        ),
    ],
)
def test_writer_read_errors_not_absence(
    step_kernel: StepKernel, monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    original = step_kernel.observe()
    step_kernel.exit()
    read = getattr(captures, "read_kernel_file")

    def checked(path: Path, limit: int, control: Any) -> KernelRead:
        if str(path) == f"/proc/{WORKER_PID}/stat":
            setattr(
                failure, "kernel_read_capture", KernelRead(str(path), b"partial", False)
            )
            raise failure
        result: KernelRead = read(path, limit, control)
        return result

    monkeypatch.setattr(captures, "read_kernel_file", checked)
    with pytest.raises(BaseException) as caught:
        observe_user_quiescence(original, Control())
    assert caught.value is failure
    assert getattr(caught.value, "slurm_kernel_capture").reads[-1].content == b"partial"


@pytest.mark.parametrize("kind", ["writer", "mount", "population", "observer"])
def test_changes_during_observation(
    step_kernel: StepKernel, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    original = step_kernel.observe()
    step_kernel.exit()
    read = getattr(captures, "read_kernel_file")
    target = {
        "writer": f"/proc/{WORKER_PID}/stat",
        "mount": f"/proc/{PID}/mountinfo",
        "population": STEP_USER + "/cgroup.events",
        "observer": f"/proc/{PID}/stat",
    }[kind]
    calls = 0

    def checked(path: Path, limit: int, control: Any) -> KernelRead:
        nonlocal calls
        if str(path) == target:
            calls += 1
            if calls == 2:
                value = {
                    "writer": WORKER_STAT.replace(b" 42 ", b" 43 "),
                    "mount": MOUNT.replace(b"138 ", b"139 "),
                    "population": b"populated 1\nfrozen 0\n",
                    "observer": step_kernel.values[f"/proc/{PID}/stat"].replace(
                        b" 42 ", b" 43 "
                    ),
                }[kind]
                return KernelRead(str(path), value, True)
        result: KernelRead = read(path, limit, control)
        return result

    monkeypatch.setattr(captures, "read_kernel_file", checked)
    with pytest.raises(ValueError):
        observe_user_quiescence(original, Control())


@pytest.mark.parametrize("stop_at", [1, 2, 10, 30, 50])
def test_stop_preserves_partial_evidence(step_kernel: StepKernel, stop_at: int) -> None:
    original = step_kernel.observe()
    step_kernel.exit()
    failure = TimeoutError("original deadline")

    class Stop(Control):
        calls = 0

        def checkpoint(self) -> float:
            self.calls += 1
            if self.calls == stop_at:
                raise failure
            return 100

    with pytest.raises(TimeoutError) as caught:
        observe_user_quiescence(original, Stop())
    assert caught.value is failure
    assert hasattr(failure, "slurm_kernel_capture")


@pytest.mark.parametrize("value", [None, {}, [], "", 0, True])
def test_invalid_original_no_reads(
    step_kernel: StepKernel, value: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Invalid input must not reach kernel IO")

    monkeypatch.setattr(captures, "read_kernel_file", forbidden)
    with pytest.raises(ValueError):
        observe_user_quiescence(value, Control())


def test_batch_is_not_dedicated_step(step_kernel: StepKernel) -> None:
    original = step_kernel.observe().model_copy(
        update={
            "step_id": "batch",
            "user_path": STEP_USER.replace("step_0", "step_batch"),
        }
    )
    with pytest.raises(ValueError, match="numeric step") as caught:
        observe_user_quiescence(original, Control())
    assert getattr(caught.value, "slurm_kernel_capture").reads == ()


@pytest.mark.parametrize(
    "status,ticks",
    [
        ("missing", 43),
        ("reused", None),
        ("reused", 42),
        ("unknown", None),
        ("reused", 0),
        ("reused", True),
    ],
)
def test_invalid_quiescence_facts(
    step_kernel: StepKernel, status: Any, ticks: Any
) -> None:
    original = step_kernel.observe()
    with pytest.raises(ValueError):
        SlurmUserQuiescence(
            original=original,
            observer=writer(),
            writer_status=status,
            replacement_start_ticks=ticks,
        )
