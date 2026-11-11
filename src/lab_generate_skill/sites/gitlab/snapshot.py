"""One exact full-tree snapshot/restore after all original native writers exit."""

import os
import threading
from pathlib import Path
from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256, NonEmptyText
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .service_contract import GitlabServiceSpec
from .service_commands import container, RUBY
from .service_files import checked
from .services import require_stop
from .snapshot_programs import INVENTORY, CLEAR_SOCKETS, SOCKET_PATHS
from .shutdown_contract import GitalyTermExit
from .workhorse_shutdown import WorkhorseTermExit


class GitlabInventory(Contract):
    schema_version: Literal["gitlab-tree-inventory/1"] = "gitlab-tree-inventory/1"
    sha256: Sha256
    files: int = Field(ge=1)
    directories: int = Field(ge=1)
    symlinks: int = Field(ge=1, le=1)
    bytes: int = Field(ge=1)


class StoppedSockets(Contract):
    schema_version: Literal["gitlab-stopped-sockets/1"] = "gitlab-stopped-sockets/1"
    removed: tuple[NonEmptyText, ...]
    absent: tuple[NonEmptyText, ...]

    @model_validator(mode="after")
    def exact_endpoints(self) -> Self:
        paths = (*self.removed, *self.absent)
        if len(paths) != len(SOCKET_PATHS) or set(paths) != set(SOCKET_PATHS):
            raise ValueError("Every original native socket must be accounted once")
        return self


class GitlabSnapshot(Contract):
    schema_version: Literal["gitlab-stopped-snapshot/2"] = "gitlab-stopped-snapshot/2"
    service: GitlabServiceSpec
    original_stop: NativeServiceQuiescence
    sockets: StoppedSockets
    inventory: GitlabInventory
    gitaly_term: GitalyTermExit | None = None
    workhorse_terms: tuple[WorkhorseTermExit, ...] = Field(default=(), max_length=2)

    @model_validator(mode="after")
    def original_shutdown(self) -> Self:
        require_stop(
            self.original_stop,
            tuple(n.original for n in self.original_stop.namespaces),
            self.gitaly_term,
            self.workhorse_terms,
        )
        if (
            self.gitaly_term is not None
            and self.gitaly_term.image_sha256 != self.service.files.image.sha256
        ):
            raise ValueError("Original snapshot changed fixed Gitaly implementation")
        if any(
            p.image_sha256 != self.service.files.image.sha256
            for p in self.workhorse_terms
        ):
            raise ValueError("Original snapshot changed fixed Workhorse implementation")
        return self


class GitlabSnapshots:
    def __init__(self, spec: GitlabServiceSpec, commands: NativeCommands) -> None:
        self.spec = GitlabServiceSpec.model_validate(spec)
        self.commands = commands
        self.owner = (os.getpid(), threading.get_ident())
        self.saving = self.restoring = False
        self.result: GitlabSnapshot | None = None
        self.restored: GitlabInventory | None = None
        self.restore_sockets: StoppedSockets | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise RuntimeError("Snapshot must stay in original GitLab worker/thread")

    def _scan(self, path: str, control: OperationControl) -> GitlabInventory:
        return GitlabInventory.model_validate_json(
            self.commands.run(
                container(self.spec, seeded=False, snapshot="read")
                + (RUBY, "-e", INVENTORY, path),
                control,
            )
        )

    def _sockets(self, control: OperationControl) -> StoppedSockets:
        return StoppedSockets.model_validate_json(
            self.commands.run(
                container(self.spec, seeded=False) + (RUBY, "-e", CLEAR_SOCKETS),
                control,
            )
        )

    def save(
        self,
        stopped: NativeServiceQuiescence,
        pins: tuple[NativeNamespaceIdentity, ...],
        control: OperationControl,
        *,
        gitaly_term: GitalyTermExit | None = None,
        workhorse_terms: tuple[WorkhorseTermExit, ...] = (),
    ) -> GitlabSnapshot:
        self._owner()
        require_stop(stopped, pins, gitaly_term, workhorse_terms)
        if (
            gitaly_term is not None
            and gitaly_term.image_sha256 != self.spec.files.image.sha256
        ):
            raise ValueError("Original snapshot changed fixed Gitaly implementation")
        if any(p.image_sha256 != self.spec.files.image.sha256 for p in workhorse_terms):
            raise ValueError("Original snapshot changed fixed Workhorse implementation")
        if self.saving or self.restoring:
            raise RuntimeError("GitLab snapshot already attempted")
        control.checkpoint()
        root = Path(self.spec.snapshot_root)
        checked(root, control)
        self.saving = True
        root.mkdir(mode=0o700)
        sockets = self._sockets(control)
        before = self._scan("/state", control)
        self.commands.run(
            container(self.spec, seeded=False, snapshot="save")
            + (
                "/bin/cp",
                "-a",
                "--",
                "/state",
                "/snapshot/state",
            ),
            control,
        )
        if (
            self._scan("/state", control) != before
            or self._scan("/snapshot/state", control) != before
        ):
            raise ValueError("Stopped original GitLab tree or snapshot changed")
        self.result = GitlabSnapshot(
            service=self.spec,
            original_stop=stopped,
            sockets=sockets,
            inventory=before,
            gitaly_term=gitaly_term,
            workhorse_terms=workhorse_terms,
        )
        control.checkpoint()
        return self.result

    def restore(
        self,
        snapshot: GitlabSnapshot,
        stopped: NativeServiceQuiescence,
        pins: tuple[NativeNamespaceIdentity, ...],
        control: OperationControl,
        *,
        gitaly_term: GitalyTermExit | None = None,
        workhorse_terms: tuple[WorkhorseTermExit, ...] = (),
    ) -> GitlabInventory:
        self._owner()
        require_stop(stopped, pins, gitaly_term, workhorse_terms)
        if (
            gitaly_term is not None
            and gitaly_term.image_sha256 != self.spec.files.image.sha256
        ):
            raise ValueError("Original restoration changed fixed Gitaly implementation")
        if any(p.image_sha256 != self.spec.files.image.sha256 for p in workhorse_terms):
            raise ValueError(
                "Original restoration changed fixed Workhorse implementation"
            )
        if (
            self.restoring
            or self.result is None
            or snapshot != self.result
            or (snapshot.service != self.spec or stopped == snapshot.original_stop)
        ):
            raise RuntimeError(
                "Restore requires original snapshot and a new stopped generation"
            )
        control.checkpoint()
        self.restoring = True
        if self._scan("/snapshot/state", control) != snapshot.inventory:
            raise ValueError("Original GitLab snapshot changed")
        self.restore_sockets = self._sockets(control)
        self._scan("/state", control)
        base = container(self.spec, seeded=False, snapshot="read")
        self.commands.run(base + (RUBY, "-e", INVENTORY, "/state", "clear"), control)
        self.commands.run(
            base + ("/bin/cp", "-a", "--", "/snapshot/state/.", "/state"), control
        )
        restored = self._scan("/state", control)
        if restored != snapshot.inventory:
            raise ValueError(
                "Restored GitLab native tree differs from original snapshot"
            )
        self.restored = restored
        control.checkpoint()
        return restored
