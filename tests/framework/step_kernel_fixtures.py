"""Known foreign-process fixtures; no production identity or cleanup permission."""

from dataclasses import dataclass
import errno
from pathlib import Path
from typing import Any

import pytest

from lab_generate_skill.adapters.slurm import kernel_capture as captures
from lab_generate_skill.adapters.slurm.kernel_files import KernelRead
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from cgroup_fixtures import (
    PID,
    USER,
    CGROUP,
    MOUNT,
    STAT,
    STATUS,
    UID_MAP,
    Control,
    writer,
)
from test_linux_cgroups import kernel as kernel
from test_slurm_probe import execution

STEP_USER = USER.replace("step_batch", "step_0")
WORKER_PID = 456
WORKER_STAT = STAT.replace(b"123 (", b"456 (")


@dataclass
class StepKernel:
    values: dict[str, bytes]
    worker: ProcessIdentity

    def observe(self) -> SlurmCgroupMembership:
        return observe_process_cgroup(execution(), self.worker, Control()).membership

    def exit(self) -> None:
        del self.values[f"/proc/{WORKER_PID}/stat"]
        self.values[STEP_USER + "/cgroup.events"] = b"populated 0\nfrozen 0\n"
        self.values[STEP_USER + "/cgroup.procs"] = b""
        self.values[STEP_USER + "/cgroup.threads"] = b""


@pytest.fixture
def step_kernel(
    kernel: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> StepKernel:
    for suffix in (
        "cgroup.type",
        "cgroup.events",
        "task_0/cgroup.type",
        "task_0/cgroup.events",
    ):
        kernel[STEP_USER + "/" + suffix] = kernel[USER + "/" + suffix]
    kernel[STEP_USER + "/task_0/cgroup.procs"] = b"456\n"
    kernel.update(
        {
            f"/proc/{WORKER_PID}/status": STATUS.replace(b"123", b"456"),
            f"/proc/{WORKER_PID}/uid_map": UID_MAP,
            f"/proc/{WORKER_PID}/stat": WORKER_STAT,
            f"/proc/{WORKER_PID}/mountinfo": MOUNT,
            f"/proc/{WORKER_PID}/cgroup": CGROUP.replace(b"step_batch", b"step_0"),
        }
    )
    original = getattr(captures, "read_kernel_file")

    def read(path: Path, limit: int, control: Any) -> KernelRead:
        if str(path) == f"/proc/{WORKER_PID}/stat" and str(path) not in kernel:
            error = FileNotFoundError(
                errno.ENOENT, "Original process is absent", str(path)
            )
            setattr(error, "kernel_read_capture", KernelRead(str(path), b"", False))
            raise error
        result: KernelRead = original(path, limit, control)
        return result

    monkeypatch.setattr(captures, "read_kernel_file", read)
    return StepKernel(kernel, writer().model_copy(update={"process_id": WORKER_PID}))
