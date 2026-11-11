"""One coherent stopped-tree snapshot and one restoration in the original worker."""

import os
from pathlib import Path
import threading
from typing import Literal
from pydantic import Field
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .service_contract import ShoppingServiceSpec
from .service_files import checked
from .service_commands import container
from .snapshot_program import INVENTORY
from .services import SERVICE_NAMES


class ShoppingInventory(Contract):
    schema_version: Literal["shopping-tree-inventory/1"] = "shopping-tree-inventory/1"
    sha256: Sha256
    files: int = Field(ge=0)
    directories: int = Field(ge=1)
    bytes: int = Field(ge=0)


class ShoppingSnapshot(Contract):
    schema_version: Literal["shopping-stopped-snapshot/1"] = (
        "shopping-stopped-snapshot/1"
    )
    service: ShoppingServiceSpec
    original_stop: NativeServiceQuiescence
    inventory: ShoppingInventory


def require_stop(facts: NativeServiceQuiescence) -> None:
    facts = NativeServiceQuiescence.model_validate(facts)
    if tuple(x.service for x in facts.masters) != SERVICE_NAMES:
        raise ValueError("Every original Shopping writer must be stopped")
    for x in facts.masters:
        if x.returncode not in ((0, 143) if x.service == "search" else (0,)):
            raise ValueError("Abnormal native stop cannot authorize directory copying")


class ShoppingSnapshots:
    def __init__(self, spec: ShoppingServiceSpec, commands: NativeCommands) -> None:
        self.spec = ShoppingServiceSpec.model_validate(spec)
        self.commands = commands
        self.owner = (os.getpid(), threading.get_ident())
        self.saving = False
        self.restoring = False
        self.result: ShoppingSnapshot | None = None
        self.restored: ShoppingInventory | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise RuntimeError("Snapshot cannot leave original Shopping worker")

    def _scan(self, path: str, control: OperationControl) -> ShoppingInventory:
        return ShoppingInventory.model_validate_json(
            self.commands.run(
                container(self.spec, seeded=False, snapshot=True)
                + ("php", "-r", INVENTORY, path),
                control,
            )
        )

    def save(
        self, stopped: NativeServiceQuiescence, control: OperationControl
    ) -> ShoppingSnapshot:
        self._owner()
        require_stop(stopped)
        if self.saving or self.restoring:
            raise RuntimeError("Shopping snapshot already attempted")
        control.checkpoint()
        root = Path(self.spec.snapshot_root)
        checked(root, control)
        self.saving = True
        root.mkdir(mode=0o700)  # collision/partial attempt is never adopted
        base = container(self.spec, seeded=False, snapshot=True)
        before = self._scan("/state", control)
        self.commands.run(
            base + ("cp", "-a", "--", "/state", "/snapshot/state"), control
        )
        if (
            self._scan("/state", control) != before
            or self._scan("/snapshot/state", control) != before
        ):
            raise ValueError("Stopped Shopping tree changed or snapshot copy differs")
        self.result = ShoppingSnapshot(
            service=self.spec, original_stop=stopped, inventory=before
        )
        control.checkpoint()
        return self.result

    def restore(
        self,
        snapshot: ShoppingSnapshot,
        stopped: NativeServiceQuiescence,
        control: OperationControl,
    ) -> ShoppingInventory:
        self._owner()
        require_stop(stopped)
        if (
            self.restoring
            or self.result is None
            or snapshot != self.result
            or snapshot.service != self.spec
            or stopped == snapshot.original_stop
        ):
            raise RuntimeError(
                "Restore requires original snapshot and a new stopped generation"
            )
        control.checkpoint()
        # All backup and current target validation precedes destructive effects.
        if self._scan("/snapshot/state", control) != snapshot.inventory:
            raise ValueError("Original stopped Shopping snapshot changed")
        self._scan("/state", control)
        self.restoring = True
        base = container(self.spec, seeded=False, snapshot=True)
        self.commands.run(base + ("php", "-r", INVENTORY, "/state", "clear"), control)
        self.commands.run(
            base + ("cp", "-a", "--", "/snapshot/state/.", "/state"), control
        )
        actual = self._scan("/state", control)
        if actual != snapshot.inventory:
            raise ValueError("Restored Shopping tree differs from original snapshot")
        self.restored = actual
        control.checkpoint()
        return actual
