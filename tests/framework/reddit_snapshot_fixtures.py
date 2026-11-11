"""Deterministic stopped-tree effects and original pins; no real native state."""

from pathlib import Path
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.reddit.service_commands import SERVICE_NAMES
from lab_generate_skill.sites.reddit.snapshot import RedditInventory
from lab_generate_skill.sites.reddit.snapshot_program import INVENTORY
from reddit_services_fixtures import Commands, Group
from test_slurm_commands import guard


def stopped(
    generation: int = 0,
) -> tuple[NativeServiceQuiescence, tuple[NativeNamespaceIdentity, ...]]:
    group = Group(generation)
    for name in SERVICE_NAMES:
        group.start(name, ("/explicit-fake-never-run",), guard())
        group.pin_namespace(name, guard())
    return group.quiesce(guard()), tuple(group.pins)


class TreeCommands(Commands):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.inventory = RedditInventory(
            sha256="a" * 64, files=5, directories=9, bytes=12345
        )
        self.scans: list[RedditInventory] = []

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        if INVENTORY not in argv:
            return super().run(argv, control)
        control.checkpoint()
        self.calls.append(argv)
        if self.error is not None and self.error in argv:
            raise OSError("injected inventory failure")
        value = (
            self.scans.pop(0) if self.scans and "clear" not in argv else self.inventory
        )
        return value.model_dump_json().encode()
