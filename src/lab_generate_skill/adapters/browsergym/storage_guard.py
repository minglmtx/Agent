"""Original guarded process observation for its browser and HTTP threads.

Linux PR_GET_PDEATHSIG is per-thread. Only the original main thread can attest
that guard; relay threads retain that observation and independently check the
same process, supervisor parent and held controller pidfd. No new guard is armed,
no numeric-PID signal, and no capability survives the original owner thread.
"""

import os
import threading
from lab_generate_skill.adapters.processes.owner_supervisor import observed_guard
from lab_generate_skill.adapters.processes.owner_pidfd import ended
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl


class OriginalBrowserProcessGuard:
    def __init__(
        self, controller: ProcessIdentity, supervisor: ProcessIdentity, owner_fd: int
    ) -> None:
        if threading.current_thread() is not threading.main_thread():
            raise OwnershipConflict("Original main browser thread must bind its guard")
        self.controller = ProcessIdentity.model_validate(controller)
        self.supervisor = ProcessIdentity.model_validate(supervisor)
        if type(owner_fd) is not int or owner_fd < 0:
            raise ValueError("Original held controller pidfd required")
        self.owner_fd = owner_fd
        self.owner = os.getpid(), threading.current_thread()
        self.original: ProcessOwnerGuard | None = None

    def observe(self, control: OperationControl) -> ProcessOwnerGuard:
        control.checkpoint()
        if os.getpid() != self.owner[0] or not self.owner[1].is_alive():
            raise OwnershipConflict(
                "Browser storage left its original owner process/thread"
            )
        if threading.current_thread() is self.owner[1]:
            actual = observed_guard(
                self.controller, self.supervisor, self.owner_fd, control
            )
            if self.original is not None and self.original != actual:
                raise OwnershipConflict("Original browser process guard changed")
            self.original = actual
        else:
            if self.original is None:
                raise OwnershipConflict(
                    "Original main thread has not observed its guard"
                )
            if (
                os.getppid() != self.supervisor.process_id
                or ended(self.owner_fd)
                or current_process_identity() != self.original.worker
            ):
                raise OwnershipConflict(
                    "Original browser process delegation is no longer live"
                )
        control.checkpoint()
        assert self.original is not None
        return self.original
