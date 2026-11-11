"""Browser-specific validation over the shared original-pidfd stop algorithm."""

from lab_generate_skill.domain.browser_step import BrowserProcessStop
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.worker_processes import (
    PinnedWorkerProcesses,
    pin_worker_processes,
)

PinnedBrowserProcesses = PinnedWorkerProcesses[BrowserProcessStop]


def pin_browser_processes(
    guard: ProcessOwnerGuard, target: SlurmStepTarget, control: OperationControl
) -> PinnedBrowserProcesses:
    return pin_worker_processes(BrowserProcessStop(guard=guard, target=target), control)
