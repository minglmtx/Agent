"""One original worker's native full-tree snapshot/restore; not task admission."""

import os
from pathlib import Path
import threading
from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .service_contract import RedditServiceSpec
from .service_commands import container
from .service_files import checked
from .services import require_stop
from .snapshot_program import INVENTORY


class RedditInventory(Contract):
    schema_version: Literal["reddit-tree-inventory/1"] = "reddit-tree-inventory/1"
    sha256: Sha256
    files: int = Field(ge=0, le=1000000)
    directories: int = Field(ge=1, le=1000000)
    bytes: int = Field(ge=0, le=2 * 1024**4)


class RedditSnapshot(Contract):
    schema_version: Literal["reddit-stopped-snapshot/1"] = "reddit-stopped-snapshot/1"
    service: RedditServiceSpec
    original_stop: NativeServiceQuiescence
    inventory: RedditInventory

    @model_validator(mode="after")
    def normal_original_stop(self) -> Self:
        require_stop(
            self.original_stop, tuple(n.original for n in self.original_stop.namespaces)
        )
        return self


class RedditSnapshots:
    def __init__(self, spec: RedditServiceSpec, commands: NativeCommands) -> None:
        self.spec = RedditServiceSpec.model_validate_json(spec.model_dump_json())
        self.commands = commands
        self.owner = os.getpid(), threading.get_ident()
        self.saving = False
        self.restoring = False
        self.result: RedditSnapshot | None = None
        self.restored: RedditInventory | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict(
                "Snapshot cannot leave original Postmill worker/thread"
            )

    def _scan(
        self, path: str, control: OperationControl, *, writable_snapshot: bool = False
    ) -> RedditInventory:
        raw = self.commands.run(
            container(
                self.spec,
                seeded=False,
                snapshot="save" if writable_snapshot else "read",
            )
            + ("/usr/local/bin/php", "-r", INVENTORY, path),
            control,
        )
        return RedditInventory.model_validate_json(raw)

    def save(
        self,
        stopped: NativeServiceQuiescence,
        pins: tuple[NativeNamespaceIdentity, ...],
        control: OperationControl,
    ) -> RedditSnapshot:
        self._owner()
        require_stop(stopped, pins)
        if self.saving or self.restoring:
            raise InvalidTransition("Postmill snapshot already attempted")
        control.checkpoint()
        root = Path(self.spec.snapshot_root)
        checked(root, control)
        self.saving = True
        root.mkdir(mode=0o700)
        before = self._scan("/state", control, writable_snapshot=True)
        self.commands.run(
            container(self.spec, seeded=False, snapshot="save")
            + ("/bin/cp", "-a", "--", "/state", "/snapshot/state"),
            control,
        )
        if (
            self._scan("/state", control, writable_snapshot=True) != before
            or self._scan("/snapshot/state", control, writable_snapshot=True) != before
        ):
            raise ValueError("Stopped native Postmill tree changed or copy differs")
        self.result = RedditSnapshot(
            service=self.spec, original_stop=stopped, inventory=before
        )
        control.checkpoint()
        return self.result

    def restore(
        self,
        snapshot: RedditSnapshot,
        stopped: NativeServiceQuiescence,
        pins: tuple[NativeNamespaceIdentity, ...],
        control: OperationControl,
    ) -> RedditInventory:
        self._owner()
        require_stop(stopped, pins)
        snapshot = RedditSnapshot.model_validate_json(snapshot.model_dump_json())
        if (
            self.restoring
            or self.result is None
            or snapshot != self.result
            or snapshot.service != self.spec
            or stopped == snapshot.original_stop
        ):
            raise InvalidTransition(
                "Restore requires original snapshot and new stopped native generation once"
            )
        control.checkpoint()
        if self._scan("/snapshot/state", control) != snapshot.inventory:
            raise ValueError("Original stopped Postmill snapshot changed")
        self._scan("/state", control)
        self.restoring = True
        base = container(self.spec, seeded=False, snapshot="read")
        self.commands.run(
            base + ("/usr/local/bin/php", "-r", INVENTORY, "/state", "clear"), control
        )
        self.commands.run(
            base + ("/bin/cp", "-a", "--", "/snapshot/state/.", "/state"), control
        )
        actual = self._scan("/state", control)
        if actual != snapshot.inventory:
            raise ValueError("Restored native Postmill tree differs from original")
        self.restored = actual
        control.checkpoint()
        return actual
