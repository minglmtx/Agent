"""Clone one complete published tree into an exclusive private node directory.

Only the acquired, supervised worker may invoke this effect. Partial destinations
are retained and never resumed/overwritten here. Historical source labels are not
opened; all content comes from the declared workspace publication.
"""

import os
from dataclasses import dataclass
from collections.abc import Mapping
from types import MappingProxyType
from pathlib import Path
import stat
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.map_runtime_inputs import MapRuntimeTree
from lab_generate_skill.domain.map_runtime_inventory import (
    MapRuntimeInventory,
    MapRuntimeMember,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.artifact_copy import (
    copy_pinned_file,
    sync_directory,
    file_identity,
    FileIdentity,
)

TreeState = dict[str, FileIdentity]


def inspect_tree(
    source: Path, inventory: MapRuntimeInventory, control: OperationControl
) -> TreeState:
    control.checkpoint()
    if source.resolve(strict=True) != source or not source.is_dir():
        raise EvidenceIntegrityError("Published Map tree must be a canonical directory")
    files = {member.file.path: member for member in inventory.files}
    directories = set(inventory.directories)
    result: TreeState = {}
    pending = [source]
    while pending:
        path = pending.pop()
        control.checkpoint()
        name = str(path.relative_to(source))
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            if name != "." and name not in directories:
                raise EvidenceIntegrityError(
                    "Undeclared directory in published Map tree"
                )
            # Each entry is bounded against the complete declared set before
            # descending; no silently ignored transient or excluded files.
            with os.scandir(path) as entries:
                for entry in entries:
                    control.checkpoint()
                    child = path / entry.name
                    relative = str(child.relative_to(source))
                    if relative not in files and relative not in directories:
                        raise EvidenceIntegrityError(
                            "Undeclared entry in published Map tree"
                        )
                    pending.append(child)
        elif stat.S_ISREG(info.st_mode) and name in files:
            member = files[name]
            if (
                info.st_size != member.file.size_bytes
                or stat.S_IMODE(info.st_mode) != member.mode
            ):
                raise EvidenceIntegrityError("Published Map file size/mode differs")
        else:
            raise EvidenceIntegrityError(
                "Published Map tree contains an alias or special file"
            )
        result[name] = file_identity(info)
    if set(result) != {".", *files, *directories}:
        raise EvidenceIntegrityError("Published Map tree is incomplete")
    return result


@dataclass(frozen=True)
class CheckedTree:
    declaration: MapRuntimeTree
    inventory: MapRuntimeInventory
    state: Mapping[str, FileIdentity]

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", MappingProxyType(dict(self.state)))


@dataclass(frozen=True)
class PreparedClone:
    checked: CheckedTree
    target: Path


def check_tree(
    declaration: MapRuntimeTree,
    inventory: MapRuntimeInventory,
    control: OperationControl,
) -> CheckedTree:
    declaration = MapRuntimeTree.model_validate(declaration)
    inventory = MapRuntimeInventory.model_validate(inventory)
    if declaration.role != inventory.role:
        raise ValueError("Published Map tree role differs")
    state = inspect_tree(Path(declaration.source_root), inventory, control)
    return CheckedTree(declaration, inventory, state)


def prepare_clone(
    declaration: MapRuntimeTree,
    inventory: MapRuntimeInventory,
    target: Path,
    control: OperationControl,
    *,
    checked: CheckedTree | None = None,
) -> PreparedClone:
    declaration = MapRuntimeTree.model_validate(declaration)
    inventory = MapRuntimeInventory.model_validate(inventory)
    source = Path(declaration.source_root)
    if declaration.role != inventory.role:
        raise ValueError("Published Map tree role differs")
    if (
        not target.is_relative_to("/tmp")
        or target == Path("/tmp")
        or target.parent.resolve(strict=True) != target.parent
        or target.is_relative_to(source)
        or source.is_relative_to(target)
    ):
        raise EvidenceIntegrityError("Exclusive canonical private Map target required")
    if checked is None:
        checked = check_tree(declaration, inventory, control)
    elif not isinstance(checked, CheckedTree) or (
        checked.declaration,
        checked.inventory,
    ) != (declaration, inventory):
        raise EvidenceIntegrityError("Preflight changed exact Map source/inventory")
    if set(checked.state) != {
        ".",
        *inventory.directories,
        *(member.file.path for member in inventory.files),
    }:
        raise EvidenceIntegrityError("Preflight lacks complete Map tree state")
    control.checkpoint()
    target.mkdir(mode=0o700)
    info = target.lstat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise EvidenceIntegrityError("Private Map tree ownership/mode differs")
    for directory in sorted(
        inventory.directories, key=lambda p: (len(Path(p).parts), p)
    ):
        control.checkpoint()
        (target / directory).mkdir(mode=0o700)
    return PreparedClone(checked, target)


def copy_member(
    clone: PreparedClone, member: MapRuntimeMember, control: OperationControl
) -> None:
    checked = clone.checked
    copy_pinned_file(
        Path(checked.declaration.source_root),
        clone.target,
        member.file,
        control,
        final_mode=member.mode,
        source_identity=checked.state[member.file.path],
    )
    control.checkpoint()


def finish_clone(clone: PreparedClone, control: OperationControl) -> None:
    checked, target = clone.checked, clone.target
    source, inventory = Path(checked.declaration.source_root), checked.inventory
    if inspect_tree(source, inventory, control) != dict(checked.state):
        raise EvidenceIntegrityError("Original published Map tree changed during clone")
    for directory in sorted(
        inventory.directories, key=lambda p: len(Path(p).parts), reverse=True
    ):
        sync_directory(target / directory)
        control.checkpoint()
    sync_directory(target)
    sync_directory(target.parent)
    control.checkpoint()


def clone_tree(
    declaration: MapRuntimeTree,
    inventory: MapRuntimeInventory,
    target: Path,
    control: OperationControl,
    *,
    checked: CheckedTree | None = None,
) -> None:
    clone = prepare_clone(declaration, inventory, target, control, checked=checked)
    for member in inventory.files:
        copy_member(clone, member, control)
    finish_clone(clone, control)
