"""Exact acquired browser file permission shared by its owned transport threads.

The writer serializes file effects. This checks immutable provenance and live
physical ownership on every I/O; controller read access cannot create files.
It grants neither task execution nor website/initial-state qualification.
"""

import os
import threading
from typing import Literal
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_current_cgroup
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.map_private_artifact import (
    MapPrivateArtifactPlan,
    MapArtifactPlan,
)
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.ports.browser_storage import (
    BrowserAcquisitionReader,
    BrowserStorageGuard,
)
from lab_generate_skill.ports.lifecycle import OperationControl


class OriginalMapBrowserAccess:
    def __init__(
        self,
        configuration: BrowserWorkerConfiguration,
        participant: Literal["worker", "controller"],
        original: BrowserAcquisitionReader,
        worker_guard: BrowserStorageGuard | None,
    ) -> None:
        self.configuration = BrowserWorkerConfiguration.model_validate(configuration)
        if self.configuration.map_inputs is None:
            raise OwnershipConflict("Original Map browser inputs required")
        if participant not in ("worker", "controller") or (participant == "worker") != (
            worker_guard is not None
        ):
            raise ValueError(
                "Only original browser worker requires its live process guard"
            )
        self.participant, self.original, self.worker_guard = (
            participant,
            original,
            worker_guard,
        )
        self.plan = self.configuration.map_inputs.plan
        self.owner = os.getpid(), threading.get_ident()
        self.stopped = threading.Event()

    def stop_new_io(self) -> None:
        self.stopped.set()

    def verify(
        self,
        plan: MapArtifactPlan,
        phase: Literal["initialize", "write", "seal", "read"],
        control: OperationControl,
    ) -> None:
        plan = MapPrivateArtifactPlan.model_validate(plan)
        if plan != self.plan or phase not in ("initialize", "write", "seal", "read"):
            raise OwnershipConflict("Browser files changed original frozen plan/phase")
        if self.participant == "controller" and phase != "read":
            raise OwnershipConflict(
                "Original controller has read-only browser file access"
            )
        if self.owner[0] != os.getpid() or (
            (self.participant == "controller" or phase in ("initialize", "seal"))
            and self.owner[1] != threading.get_ident()
        ):
            raise OwnershipConflict(
                "Browser file capability left its original process/owner thread"
            )
        self._open()
        control.checkpoint()
        original = self.original.read(self.configuration, control)
        if (
            original.spec.configuration != self.configuration
            or original.spec.token != plan.token
        ):
            raise OwnershipConflict("Browser original reader changed frozen resource")
        allowed = (
            ("acquired", "closing", "closed", "quarantined")
            if (self.participant == "controller")
            else ("acquired", "closing")
        )
        if original.record.state not in allowed:
            raise OwnershipConflict(
                "Original browser state does not permit file access"
            )
        if original.record.state == "closing" and phase == "initialize":
            raise OwnershipConflict("Closing browser cannot initialize new collection")
        prepared = original.acquired.details.prepared
        guard = prepared.owner_guard
        identity = guard.worker if self.participant == "worker" else guard.controller
        if current_process_identity() != identity:
            raise OwnershipConflict(
                "Browser file caller is not original acquired participant"
            )
        expected = (
            prepared.step.controller.target.worker
            if self.participant == "worker"
            else original.spec.slurm.parent
        )
        actual = observe_current_cgroup(
            original.spec.slurm.execution, identity, control
        ).membership
        same = (
            actual.model_dump(exclude={"mount_id"})
            == expected.model_dump(exclude={"mount_id"})
            if self.participant == "worker"
            else actual == expected
        )
        if not same:
            raise OwnershipConflict(
                "Browser file participant left original physical Slurm cgroup"
            )
        if (
            self.worker_guard is not None
            and self.worker_guard.observe(control) != guard
        ):
            raise OwnershipConflict(
                "Browser live guard differs from original acquisition"
            )
        control.checkpoint()
        self._open()

    def _open(self) -> None:
        if self.stopped.is_set():
            raise InvalidTransition("Original browser file capability is stopped")
