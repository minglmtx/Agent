"""One original acquired participant/physical cgroup check shared by site stores."""

import os
import threading
from typing import Literal
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_storage_original import SiteStorageOriginal
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.site_storage import SiteAcquisitionReader, SiteWorkerGuard
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_current_cgroup


def observe_original(
    configuration: SiteWorkerConfiguration,
    participant: Literal["worker", "controller"],
    reader: SiteAcquisitionReader,
    worker_guard: SiteWorkerGuard | None,
    owner: tuple[int, int],
    control: OperationControl,
    *,
    cleanup: bool = False,
) -> SiteStorageOriginal:
    if owner != (os.getpid(), threading.get_ident()):
        raise OwnershipConflict(
            "Site storage capability left its original process/thread"
        )
    control.checkpoint()
    original = reader.read(configuration, control)
    if original.spec.configuration != configuration:
        raise OwnershipConflict("Storage original reader changed frozen site")
    allowed = (
        ("acquired", "closing", "closed", "quarantined")
        if cleanup or participant == "controller"
        else ("acquired",)
    )
    if original.record.state not in allowed:
        raise OwnershipConflict(
            "Original site state does not permit this private storage use"
        )
    guard = original.acquired.details.ready.worker.owner_guard
    identity = guard.worker if participant == "worker" else guard.controller
    if current_process_identity() != identity:
        raise OwnershipConflict("Private store caller is not original site participant")
    expected = (
        original.acquired.details.ready.controller.target.worker
        if participant == "worker"
        else original.spec.slurm.parent
    )
    observed = observe_current_cgroup(
        original.spec.slurm.execution, identity, control
    ).membership
    # Ready was observed through the original controller's mount view.
    # SlurmCgroupMembership.mount_id is local to that observer, whereas
    # device and user/task inodes identify the physical original subtree.
    # The controller still compares in its original view, including ID.
    same = (
        observed.model_dump(exclude={"mount_id"})
        == expected.model_dump(exclude={"mount_id"})
        if participant == "worker"
        else observed == expected
    )
    if not same:
        raise OwnershipConflict("Private store participant left original Slurm cgroup")
    if worker_guard is not None and worker_guard.observe(control) != guard:
        raise OwnershipConflict("Original guarded site worker changed")
    control.checkpoint()
    return original
