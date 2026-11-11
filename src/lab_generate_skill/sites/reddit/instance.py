"""Original private Postmill instance across snapshot, restore and resume.

Admission and final whole-resource closure belong to the registered owner. This
component keeps all generation handles and never releases the port lease or
removes the private root, including on partial initialization or cleanup failure.
"""

from collections.abc import Callable
import os
from pathlib import Path
import stat
import threading
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.site_files import SiteFiles
from lab_generate_skill.ports.local_ports import LocalPorts, LocalPortLease
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.native_quiescence import QuiescentNativeServices
from .service_contract import RedditPorts, RedditServiceSpec, require_original_image
from .service_files import checked
from .media_initialization_contract import MediaInitialization
from .services import RedditGeneration, seed
from .snapshot import RedditInventory, RedditSnapshot, RedditSnapshots
from .progress import RedditPhase, RedditProgress


class RedditInstance:
    def __init__(
        self,
        files_plan: SiteFilesPlan,
        *,
        files: SiteFiles,
        ports: LocalPorts,
        commands: NativeCommands,
        services: Callable[[str, OperationControl], QuiescentNativeServices],
        progress: RedditProgress | None = None,
    ) -> None:
        self.files_plan = SiteFilesPlan.model_validate_json(
            files_plan.model_dump_json()
        )
        require_original_image(self.files_plan)
        self.files, self.ports, self.commands = files, ports, commands
        self.services_factory = services
        self.progress = progress
        self.owner = os.getpid(), threading.get_ident()
        self.state = "new"
        self.lease: LocalPortLease | None = None
        self.spec: RedditServiceSpec | None = None
        self.generations: list[RedditGeneration] = []
        self.snapshots: RedditSnapshots | None = None
        self.media_initialization: MediaInitialization | None = None
        self.snapshot: RedditSnapshot | None = None
        self.restored: RedditInventory | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict(
                "Postmill lifecycle requires original worker/thread"
            )

    def _phase(self, phase: RedditPhase) -> None:
        if self.progress is not None:
            self.progress(phase)

    def prepare(self, control: OperationControl) -> RedditServiceSpec:
        self._owner()
        if self.state != "new":
            raise InvalidTransition("Original Postmill preparation already attempted")
        control.checkpoint()
        self.state = "preparing"
        try:
            self._phase(RedditPhase.IMAGE_BEGIN)
            self.files.stage(self.files_plan, control)
            self._phase(RedditPhase.IMAGE_READY)
            for name in ["control", "runtime"]:
                path = Path(self.files_plan.node_root) / name
                checked(path, control)
                path.mkdir(mode=0o700)
            self.lease = self.ports.reserve(2, control)
            if len(self.lease.ports) != 2:
                raise ValueError("Original Postmill lease requires two ports")
            self.spec = RedditServiceSpec(
                files=self.files_plan,
                ports=RedditPorts(
                    web=self.lease.ports[0], database=self.lease.ports[1]
                ),
            )
            self._phase(RedditPhase.SEED_BEGIN)
            self.media_initialization = seed(self.spec, self.commands, control)
            self._phase(RedditPhase.SEED_READY)
            self.snapshots = RedditSnapshots(self.spec, self.commands)
            self.state = "prepared"
            return self.spec
        except BaseException:
            self.state = "failed"
            raise

    def _new_generation(self, control: OperationControl, *, initialize: bool) -> str:
        assert self.spec is not None
        path = Path(self.files_plan.log_root) / f"generation-{len(self.generations)+1}"
        checked(path, control)
        path.mkdir(mode=0o700)
        group = self.services_factory(str(path), control)
        generation = RedditGeneration(
            self.spec, self.commands, group, progress=self.progress
        )
        self.generations.append(generation)  # retain before the first start effect
        return generation.start(control, initialize=initialize)

    def _clear_runtime(self, control: OperationControl) -> None:
        assert self.spec is not None
        root = Path(self.spec.runtime_root)
        checked(root, control)
        entries = list(root.iterdir())
        for path in entries:
            control.checkpoint()
            value = path.lstat()
            if (
                not (stat.S_ISREG(value.st_mode) or stat.S_ISSOCK(value.st_mode))
                or value.st_nlink != 1
            ):
                raise ValueError(
                    "Unexpected original Postmill runtime entry; preserve isolation"
                )
        archive = (
            Path(self.files_plan.log_root)
            / f"generation-{len(self.generations)}"
            / "runtime"
        )
        checked(archive, control)
        archive.mkdir(mode=0o700)
        for path in entries:
            control.checkpoint()
            if stat.S_ISREG(path.lstat().st_mode):
                path.rename(archive / path.name)
            else:
                path.unlink()

    def start(self, control: OperationControl) -> str:
        self._owner()
        if self.state != "prepared":
            raise InvalidTransition(
                "Postmill start requires original prepared instance"
            )
        control.checkpoint()
        self.state = "starting"
        try:
            endpoint = self._new_generation(control, initialize=True)
            self.state = "ready"
            return endpoint
        except BaseException:
            self.state = "failed"
            raise

    def snapshot_and_restart(self, control: OperationControl) -> RedditSnapshot:
        self._owner()
        if self.state != "ready" or self.snapshot is not None or self.snapshots is None:
            raise InvalidTransition("One original pre-task Postmill snapshot required")
        control.checkpoint()
        self.state = "snapshotting"
        try:
            self._phase(RedditPhase.SNAPSHOT_BEGIN)
            current = self.generations[-1]
            facts = current.quiesce(control)
            self.snapshot = self.snapshots.save(facts, current.pins, control)
            current.stop(control)
            self._clear_runtime(control)
            self._new_generation(control, initialize=False)
            self.state = "snapshotted"
            self._phase(RedditPhase.SNAPSHOT_READY)
            return self.snapshot
        except BaseException:
            self.state = "failed"
            raise

    def restore(
        self, snapshot: RedditSnapshot, control: OperationControl
    ) -> RedditInventory:
        self._owner()
        if (
            self.state != "snapshotted"
            or self.snapshots is None
            or self.snapshot is None
            or snapshot != self.snapshot
        ):
            raise InvalidTransition("Restore requires this original Postmill snapshot")
        control.checkpoint()
        self.state = "restoring"
        try:
            self._phase(RedditPhase.RESTORE_BEGIN)
            current = self.generations[-1]
            facts = current.quiesce(control)
            self.restored = self.snapshots.restore(
                snapshot, facts, current.pins, control
            )
            current.stop(control)
            self._clear_runtime(control)
            self.state = "restored"
            self._phase(RedditPhase.RESTORE_READY)
            return self.restored
        except BaseException:
            self.state = "failed"
            raise

    def resume(self, control: OperationControl) -> str:
        self._owner()
        if self.state != "restored" or self.restored is None:
            raise InvalidTransition(
                "Resume requires original verified Postmill restoration"
            )
        control.checkpoint()
        self.state = "resuming"
        try:
            self._phase(RedditPhase.RESUME_BEGIN)
            endpoint = self._new_generation(control, initialize=False)
            self.state = "resumed"
            self._phase(RedditPhase.RESUME_READY)
            return endpoint
        except BaseException:
            self.state = "failed"
            raise

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self._owner()
        self.state = "stopping"
        errors: list[BaseException] = []
        facts: tuple[NativeServiceExit, ...] = ()
        for generation in reversed(self.generations):
            if generation.state == "stopped":
                continue
            try:
                facts += generation.stop(control)
            except BaseException as error:
                errors.append(error)
        self.state = "failed" if errors else "stopped"
        if errors:
            raise BaseExceptionGroup(
                "Original Postmill generation cleanup incomplete", errors
            )
        return facts
