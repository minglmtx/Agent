"""One private Shopping lifecycle; original ports and all generations retained.

The enclosing registered resource owns admission, supervision and final cleanup.
This component never releases the port lease or removes the instance directory.
"""

from collections.abc import Callable
import os
from pathlib import Path
import stat
import threading
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.site_files import SiteFiles
from lab_generate_skill.ports.local_ports import LocalPorts, LocalPortLease
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.native_quiescence import QuiescentNativeServices
from .service_contract import ShoppingPorts, ShoppingServiceSpec
from .service_files import checked
from .services import ShoppingGeneration, seed
from .snapshot import ShoppingInventory, ShoppingSnapshot, ShoppingSnapshots
from .progress import ShoppingPhase, ShoppingProgress


class ShoppingInstance:
    def __init__(
        self,
        files_plan: SiteFilesPlan,
        *,
        files: SiteFiles,
        ports: LocalPorts,
        commands: NativeCommands,
        services: Callable[[str, OperationControl], QuiescentNativeServices],
        progress: ShoppingProgress | None = None,
    ) -> None:
        self.files_plan = SiteFilesPlan.model_validate(files_plan)
        self.files, self.ports, self.commands = files, ports, commands
        self.services_factory = services
        self.progress = progress
        self.owner = (os.getpid(), threading.get_ident())
        self.state = "new"
        self.lease: LocalPortLease | None = None
        self.spec: ShoppingServiceSpec | None = None
        self.generations: list[ShoppingGeneration] = []
        self.snapshots: ShoppingSnapshots | None = None
        self.snapshot: ShoppingSnapshot | None = None
        self.static_provenance: bytes | None = None
        self.restored: ShoppingInventory | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise RuntimeError("Shopping lifecycle requires original worker/thread")

    def _phase(self, phase: ShoppingPhase) -> None:
        if self.progress is not None:
            self.progress(phase)

    def prepare(self, control: OperationControl) -> ShoppingServiceSpec:
        self._owner()
        if self.state != "new":
            raise RuntimeError("Shopping preparation already attempted")
        control.checkpoint()
        self.state = "preparing"
        try:
            self._phase(ShoppingPhase.IMAGE_BEGIN)
            self.files.stage(self.files_plan, control)
            self._phase(ShoppingPhase.IMAGE_READY)
            for name in ("control", "runtime"):
                path = Path(self.files_plan.node_root) / name
                checked(path, control)
                path.mkdir(mode=0o700)
            self.lease = self.ports.reserve(5, control)
            if len(self.lease.ports) != 5:
                raise ValueError("Original Shopping lease must contain five ports")
            p = self.lease.ports
            self.spec = ShoppingServiceSpec(
                files=self.files_plan,
                ports=ShoppingPorts(
                    web=p[0], database=p[1], redis=p[2], search=p[3], transport=p[4]
                ),
            )
            self._phase(ShoppingPhase.SEED_BEGIN)
            self.static_provenance = seed(self.spec, self.commands, control)
            self._phase(ShoppingPhase.SEED_READY)
            self.snapshots = ShoppingSnapshots(self.spec, self.commands)
            self.state = "prepared"
            return self.spec
        except BaseException:
            self.state = "failed"
            raise

    def _new_generation(self, control: OperationControl, *, configure: bool) -> str:
        assert self.spec is not None
        path = (
            Path(self.files_plan.log_root) / f"generation-{len(self.generations) + 1}"
        )
        checked(path, control)
        path.mkdir(mode=0o700)
        group = self.services_factory(str(path), control)
        generation = ShoppingGeneration(
            self.spec, self.commands, group, progress=self.progress
        )
        self.generations.append(generation)  # keep original handles before effects
        return generation.start(control, configure=configure)

    def _clear_runtime(self, control: OperationControl) -> None:
        # Only after the current generation's exact namespace exit was proved.
        # Runtime holds sockets/PIDs and diagnostics, never PHP sessions or mail.
        assert self.spec is not None
        root = Path(self.spec.runtime_root)
        checked(root, control)
        entries = list(root.iterdir())
        for path in entries:
            control.checkpoint()
            s = path.lstat()
            if (
                not (stat.S_ISREG(s.st_mode) or stat.S_ISSOCK(s.st_mode))
                or s.st_nlink != 1
            ):
                raise ValueError("Unexpected private runtime entry; retain isolation")
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
            raise RuntimeError("Shopping start requires original prepared instance")
        control.checkpoint()
        self.state = "starting"
        try:
            endpoint = self._new_generation(control, configure=True)
            self.state = "ready"
            return endpoint
        except BaseException:
            self.state = "failed"
            raise

    def snapshot_and_restart(self, control: OperationControl) -> ShoppingSnapshot:
        self._owner()
        if self.state != "ready" or self.snapshot is not None or self.snapshots is None:
            raise RuntimeError("One original pre-task Shopping snapshot required")
        control.checkpoint()
        self.state = "snapshotting"
        try:
            current = self.generations[-1]
            stopped = current.quiesce(control)
            self.snapshot = self.snapshots.save(stopped, control)
            current.stop(control)
            self._clear_runtime(control)
            self._new_generation(control, configure=False)
            self.state = "snapshotted"
            return self.snapshot
        except BaseException:
            self.state = "failed"
            raise

    def restore(
        self, snapshot: ShoppingSnapshot, control: OperationControl
    ) -> ShoppingInventory:
        self._owner()
        if (
            self.state != "snapshotted"
            or self.snapshots is None
            or self.snapshot is None
            or snapshot != self.snapshot
        ):
            raise RuntimeError("Restore requires this original Shopping snapshot")
        control.checkpoint()
        self.state = "restoring"
        try:
            current = self.generations[-1]
            stopped = current.quiesce(control)
            self.restored = self.snapshots.restore(snapshot, stopped, control)
            current.stop(control)
            self._clear_runtime(control)
            self.state = "restored"
            return self.restored
        except BaseException:
            self.state = "failed"
            raise

    def resume(self, control: OperationControl) -> str:
        self._owner()
        if self.state != "restored" or self.restored is None:
            raise RuntimeError("Resume requires original verified Shopping restoration")
        control.checkpoint()
        self.state = "resuming"
        try:
            endpoint = self._new_generation(control, configure=False)
            self.state = "resumed"
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
        if errors:
            self.state = "failed"
            group = BaseExceptionGroup(
                "Shopping original service cleanup failed", errors
            )
            setattr(group, "service_exits", facts)
            raise group
        self.state = "stopped"
        return facts
