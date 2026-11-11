"""Known worker observation: normal, namespace/identity boundaries and failures."""

from pathlib import Path
from typing import Any

import pytest

from lab_generate_skill.adapters.slurm import kernel_capture as captures
from lab_generate_skill.adapters.slurm.linux_cgroups import (
    observe_current_cgroup,
    observe_process_cgroup,
)
from lab_generate_skill.adapters.slurm.kernel_files import KernelRead
from cgroup_fixtures import PID, UID, MOUNT, STATUS, STAT, Control, writer
from step_kernel_fixtures import (
    STEP_USER,
    WORKER_PID,
    StepKernel,
    step_kernel as step_kernel,
)
from test_slurm_probe import execution
from test_linux_cgroups import kernel as kernel


def test_known_worker_and_repeat(step_kernel: StepKernel) -> None:
    first = observe_process_cgroup(execution(), step_kernel.worker, Control())
    second = observe_process_cgroup(execution(), step_kernel.worker, Control())
    assert first == second
    assert first.membership.step_id == "0"
    assert first.membership.user_path == STEP_USER
    assert first.membership.writer.process_id != PID
    assert any(r.path == f"/proc/{PID}/status" for r in first.capture.reads)
    with pytest.raises(ValueError, match="this original Linux writer"):
        observe_current_cgroup(execution(), step_kernel.worker, Control())


@pytest.mark.parametrize("worker_mount_id", [139, 1044, 999999])
def test_distinct_mount_ids_same_full_filesystem(
    step_kernel: StepKernel, worker_mount_id: int
) -> None:
    path = f"/proc/{WORKER_PID}/mountinfo"
    step_kernel.values[path] = MOUNT.replace(
        b"138 ", (str(worker_mount_id) + " ").encode()
    )
    membership = step_kernel.observe()
    assert membership.mount_id == 138
    assert membership.writer == step_kernel.worker


@pytest.mark.parametrize("pid", [PID, WORKER_PID])
def test_each_mount_id_must_remain_stable(
    step_kernel: StepKernel, monkeypatch: pytest.MonkeyPatch, pid: int
) -> None:
    original = getattr(captures, "read_kernel_file")
    calls = 0

    def read(path: Path, limit: int, control: Any) -> KernelRead:
        nonlocal calls
        result: KernelRead = original(path, limit, control)
        if str(path) == f"/proc/{pid}/mountinfo":
            calls += 1
            if calls == 2:
                return KernelRead(
                    str(path), result.content.replace(b"138 ", b"139 "), True
                )
        return result

    monkeypatch.setattr(captures, "read_kernel_file", read)
    with pytest.raises(ValueError, match="changed during"):
        step_kernel.observe()


@pytest.mark.parametrize("pid", [PID, WORKER_PID])
@pytest.mark.parametrize(
    "suffix,change",
    [
        ("status", (b"NSpid:\t", b"NSpid:\t1 ")),
        ("status", (b"1000 1000 1000 1000", b"1000 0 1000 1000")),
        ("status", (b"CapEff:\t0000000000000000", b"CapEff:\t0000000000000001")),
        ("uid_map", (b"0 0", b"0 1000")),
        ("mountinfo", (b"0:26", b"0:27")),
    ],
)
def test_observer_and_worker_mismatch(
    step_kernel: StepKernel, pid: int, suffix: str, change: tuple[bytes, bytes]
) -> None:
    path = f"/proc/{pid}/{suffix}"
    step_kernel.values[path] = step_kernel.values[path].replace(*change)
    with pytest.raises(ValueError) as caught:
        step_kernel.observe()
    assert getattr(caught.value, "slurm_kernel_capture").reads


@pytest.mark.parametrize(
    "field,value",
    [
        ("process_id", 0),
        ("process_id", True),
        ("start_ticks", 43),
        ("node_id", "foreign"),
        ("boot_id", "00000000-0000-0000-0000-000000000000"),
    ],
)
def test_wrong_known_incarnation(
    step_kernel: StepKernel, field: str, value: object
) -> None:
    changed = step_kernel.worker.model_copy(update={field: value})
    with pytest.raises(ValueError):
        observe_process_cgroup(execution(), changed, Control())


def test_foreign_writer_missing_and_replaced(step_kernel: StepKernel) -> None:
    step_kernel.exit()
    with pytest.raises(FileNotFoundError):
        step_kernel.observe()
    step_kernel.values[f"/proc/{WORKER_PID}/stat"] = STAT.replace(
        b"123 (", b"456 ("
    ).replace(b" 42 ", b" 99 ")
    with pytest.raises(ValueError, match="incarnation"):
        step_kernel.observe()


def test_foreign_writer_changes_during_observation(
    step_kernel: StepKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = getattr(captures, "read_kernel_file")
    calls = 0

    def read(path: Path, limit: int, control: Any) -> KernelRead:
        nonlocal calls
        result: KernelRead = original(path, limit, control)
        if str(path) == f"/proc/{WORKER_PID}/stat":
            calls += 1
            if calls == 2:
                return KernelRead(
                    str(path), result.content.replace(b" 42 ", b" 99 "), True
                )
        return result

    monkeypatch.setattr(captures, "read_kernel_file", read)
    with pytest.raises(ValueError, match="incarnation"):
        step_kernel.observe()
