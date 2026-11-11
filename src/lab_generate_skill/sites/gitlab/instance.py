"""One private GitLab instance; the enclosing resource retains lifecycle rights.

The full restored generation starts inside restore. A separate once-only resume
confirms that original new generation; it never launches a fourth replacement.
No lease release or root deletion is performed here.
"""

from collections.abc import Callable
import os
from pathlib import Path
import threading
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.site_files import SiteFiles
from lab_generate_skill.ports.local_ports import LocalPorts, LocalPortLease
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.native_quiescence import QuiescentNativeServices
from lab_generate_skill.ports.lifecycle import OperationControl
from .service_contract import GitlabPorts, GitlabServiceSpec, peer_user
from .service_files import checked
from .services import GitlabGeneration, seed
from .snapshot import GitlabSnapshots, GitlabSnapshot, GitlabInventory
from .progress import GitlabPhase, GitlabProgress


class GitlabInstance:
    def __init__(
        self,
        files_plan: SiteFilesPlan,
        *,
        database_peer_user: str,
        files: SiteFiles,
        ports: LocalPorts,
        commands: NativeCommands,
        services: Callable[[str, OperationControl], QuiescentNativeServices],
        progress: GitlabProgress | None = None,
    ) -> None:
        self.files_plan = SiteFilesPlan.model_validate(files_plan)
        self.database_peer_user = peer_user(database_peer_user)
        self.files, self.ports, self.commands = files, ports, commands
        self.services_factory, self.progress = services, progress
        self.owner = (os.getpid(), threading.get_ident())
        self.state = "new"
        self.lease: LocalPortLease | None = None
        self.spec: GitlabServiceSpec | None = None
        self.generations: list[GitlabGeneration] = []
        self.snapshots: GitlabSnapshots | None = None
        self.snapshot: GitlabSnapshot | None = None
        self.restored: GitlabInventory | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise RuntimeError("GitLab lifecycle must stay with original worker/thread")

    def _phase(self, phase: GitlabPhase) -> None:
        if self.progress is not None:
            self.progress(phase)

    def prepare(self, control: OperationControl) -> GitlabServiceSpec:
        self._owner()
        if self.state != "new":
            raise RuntimeError("GitLab preparation already attempted")
        control.checkpoint()
        self.state = "preparing"
        try:
            self._phase(GitlabPhase.IMAGE_BEGIN)
            self.files.stage(self.files_plan, control)
            self._phase(GitlabPhase.IMAGE_READY)
            path = Path(self.files_plan.node_root) / "control"
            checked(path, control)
            path.mkdir(mode=0o700)
            self.lease = self.ports.reserve(2, control)
            if len(self.lease.ports) != 2:
                raise ValueError("Exactly two original GitLab ports required")
            self.spec = GitlabServiceSpec(
                files=self.files_plan,
                database_peer_user=self.database_peer_user,
                ports=GitlabPorts(web=self.lease.ports[0], metrics=self.lease.ports[1]),
            )
            state = Path(self.files_plan.state_root)
            checked(state, control)
            if not state.is_dir() or any(state.iterdir()):
                raise ValueError("Original empty private GitLab seed required")
            self._phase(GitlabPhase.SEED_BEGIN)
            seed(self.spec, self.commands, control)
            self._phase(GitlabPhase.SEED_READY)
            self.snapshots = GitlabSnapshots(self.spec, self.commands)
            self.state = "prepared"
            return self.spec
        except BaseException:
            self.state = "failed"
            raise

    def _new_generation(self, control: OperationControl) -> str:
        assert self.spec is not None
        path = Path(self.files_plan.log_root) / f"generation-{len(self.generations)+1}"
        checked(path, control)
        path.mkdir(mode=0o700)
        generation = GitlabGeneration(
            self.spec,
            self.commands,
            self.services_factory(str(path), control),
            progress=self.progress,
            log_root=path,
        )
        self.generations.append(generation)
        return generation.start(control)

    def start(self, control: OperationControl) -> str:
        self._owner()
        if self.state != "prepared":
            raise RuntimeError("GitLab start requires original prepared instance")
        self.state = "starting"
        try:
            endpoint = self._new_generation(control)
            self.state = "ready"
            return endpoint
        except BaseException:
            self.state = "failed"
            raise

    def snapshot_and_restart(self, control: OperationControl) -> GitlabSnapshot:
        self._owner()
        if self.state != "ready" or self.snapshot is not None or self.snapshots is None:
            raise RuntimeError("One original pre-task GitLab snapshot required")
        self.state = "snapshotting"
        try:
            current = self.generations[-1]
            stopped = current.quiesce(control)
            self.snapshot = self.snapshots.save(
                stopped,
                current.pins,
                control,
                gitaly_term=current.gitaly_term,
                workhorse_terms=current.workhorse_terms,
            )
            current.stop(control)
            self._new_generation(control)
            self.state = "snapshotted"
            return self.snapshot
        except BaseException:
            self.state = "failed"
            raise

    def restore(
        self, snapshot: GitlabSnapshot, control: OperationControl
    ) -> GitlabInventory:
        self._owner()
        if (
            self.state != "snapshotted"
            or self.snapshots is None
            or self.snapshot is None
            or snapshot != self.snapshot
        ):
            raise RuntimeError("Restore requires this original GitLab snapshot")
        self.state = "restoring"
        try:
            current = self.generations[-1]
            stopped = current.quiesce(control)
            self.restored = self.snapshots.restore(
                snapshot,
                stopped,
                current.pins,
                control,
                gitaly_term=current.gitaly_term,
                workhorse_terms=current.workhorse_terms,
            )
            current.stop(control)
            self._new_generation(control)
            self.state = "restored"
            return self.restored
        except BaseException:
            self.state = "failed"
            raise

    def resume(self, control: OperationControl) -> str:
        self._owner()
        if self.state != "restored" or self.spec is None:
            raise RuntimeError(
                "One confirmation of the original restored GitLab generation required"
            )
        self.state = "confirming_restored"
        try:
            current = self.generations[-1]
            current.confirm_healthy(control)
            self.state = "resumed"
            return self.spec.endpoint
        except BaseException:
            self.state = "failed"
            raise

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self._owner()
        self.state = "stopping"
        exits: tuple[NativeServiceExit, ...] = ()
        errors: list[BaseException] = []
        for generation in reversed(self.generations):
            try:
                exits += generation.stop(control)
            except BaseException as error:
                errors.append(error)
        self.state = "failed" if errors else "stopped"
        if errors:
            raise BaseExceptionGroup("Original GitLab service cleanup failed", errors)
        return exits
