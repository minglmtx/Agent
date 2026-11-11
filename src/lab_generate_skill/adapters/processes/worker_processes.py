"""Hold exact original worker/supervisor pidfds for bounded resource cleanup.

Only called after actual original step membership was verified. The worker is
stopped first, letting its original supervisor reap it. If that supervisor does
not exit during a short bounded observation, stop its exact held pidfd too.
No PID signal fallback, rediscovery, whole-job cancellation or execution retry.
Pidfd exit observations never replace separate Slurm/cgroup closure evidence.
"""

import os
import threading
from contextlib import ExitStack
from lab_generate_skill.adapters.processes.owner_pidfd import pinned_owner, ended
from lab_generate_skill.adapters.processes.linux_pidfd import kill_pidfd
from lab_generate_skill.domain.worker_processes import CpuProcessStopFacts
from typing import Generic, TypeVar

Facts = TypeVar("Facts", bound=CpuProcessStopFacts)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl


class PinnedWorkerProcesses(Generic[Facts]):
    def __init__(
        self, facts: Facts, descriptors: tuple[int, int], stack: ExitStack
    ) -> None:
        self._facts = facts
        self._worker, self._supervisor = descriptors
        self._stack = stack
        self._context = (os.getpid(), threading.get_ident())
        self._closed = False

    @property
    def facts(self) -> Facts:
        return self._facts

    def _owned(self) -> None:
        if self._closed or self._context != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Worker process handles are closed or foreign")

    def _observe(self) -> None:
        self._facts = self._facts.model_copy(
            update={
                "worker_exit_observed": ended(self._worker),
                "supervisor_exit_observed": ended(self._supervisor),
            }
        )

    def stop(self, control: OperationControl) -> Facts:
        self._owned()
        control.checkpoint()
        self._observe()
        if (
            not self._facts.worker_exit_observed
            and not self._facts.worker_signal_requested
        ):
            self._facts = self._facts.model_copy(
                update={"worker_signal_requested": True}
            )
            try:
                kill_pidfd(self._worker)
            except ProcessLookupError:
                pass  # Independently observe the held descriptor; never infer exit.
        # Give the original supervisor its bounded normal child-reaping path.
        for _ in range(10):
            self._observe()
            if (
                self._facts.worker_exit_observed
                and self._facts.supervisor_exit_observed
            ):
                return self._facts
            control.wait(0.05)
        if (
            not self._facts.supervisor_exit_observed
            and not self._facts.supervisor_signal_requested
        ):
            control.checkpoint()
            self._facts = self._facts.model_copy(
                update={"supervisor_signal_requested": True}
            )
            try:
                kill_pidfd(self._supervisor)
            except ProcessLookupError:
                pass
        while True:
            control.checkpoint()
            self._observe()
            if (
                self._facts.worker_exit_observed
                and self._facts.supervisor_exit_observed
            ):
                return self._facts
            control.wait(0.05)

    def close(self) -> None:
        if self._closed:
            return
        self._owned()
        self._closed = True
        self._stack.close()


def pin_worker_processes(
    facts: Facts, control: OperationControl
) -> PinnedWorkerProcesses[Facts]:
    with ExitStack() as stack:
        worker = stack.enter_context(pinned_owner(facts.guard.worker, control))
        supervisor = stack.enter_context(pinned_owner(facts.guard.supervisor, control))
        control.checkpoint()
        return PinnedWorkerProcesses(facts, (worker, supervisor), stack.pop_all())
