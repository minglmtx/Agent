"""Verify original closed-site image/routing bytes, never clone or mutate them."""

import hashlib
import os
from pathlib import Path
import stat
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.map_runtime_inputs import MapRuntimeInputs
from lab_generate_skill.domain.map_runtime_inventory import MapRuntimeInventory
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.artifact_copy import (
    file_identity,
    FileIdentity,
    close_all,
)
from .tree_copy import inspect_tree


def verify_file(
    path: Path, pin: ReleaseFile, control: OperationControl
) -> FileIdentity:
    control.checkpoint()
    if path.resolve(strict=True) != path:
        raise EvidenceIntegrityError("Readonly Map input uses an alias")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    primary: BaseException | None = None
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_size != pin.size_bytes
            or bool(before.st_mode & 0o111) != pin.executable
        ):
            raise EvidenceIntegrityError("Readonly Map input type/owner/size differs")
        remaining = pin.size_bytes + 1
        digest = hashlib.sha256()
        while remaining:
            control.checkpoint()
            data = os.read(fd, min(1024 * 1024, remaining))
            if not data:
                break
            remaining -= len(data)
            digest.update(data)
        identity = file_identity(before)
        if (
            remaining != 1
            or digest.hexdigest() != pin.sha256
            or file_identity(os.fstat(fd)) != identity
            or file_identity(path.lstat()) != identity
        ):
            raise EvidenceIntegrityError("Readonly Map input bytes or identity changed")
        control.checkpoint()
        return identity
    except BaseException as error:
        primary = error
        raise
    finally:
        close_all((fd,), primary)


def verify_readonly_inputs(
    plan: MapRuntimeInputs, routing: MapRuntimeInventory, control: OperationControl
) -> dict[Path, FileIdentity]:
    selected = plan.readonly_inputs
    if selected is None or routing.role != "routing":
        raise ValueError("Explicit original readonly routing input required")
    root = Path(selected.source_node_root)
    if root.resolve(strict=True) != root:
        raise EvidenceIntegrityError("Readonly Map root uses an alias")
    info = root.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise EvidenceIntegrityError("Original private Map root owner/mode differs")
    paths = {root: file_identity(info)}
    for image in plan.images:
        path = Path(plan.node_image(image.role))
        paths[path] = verify_file(path, image.file, control)
        if paths[path][-1] & 0o222:
            raise EvidenceIntegrityError("Original shared Map image is writable")
    tree = Path(plan.node_tree("routing"))
    before = inspect_tree(tree, routing, control)
    for member in routing.files:
        path = tree / member.file.path
        identity = verify_file(path, member.file, control)
        if identity != before[member.file.path]:
            raise EvidenceIntegrityError("Readonly routing changed after inspection")
    if inspect_tree(tree, routing, control) != before:
        raise EvidenceIntegrityError("Readonly routing changed during verification")
    paths.update({tree / name: identity for name, identity in before.items()})
    return paths


def recheck_readonly_inputs(
    paths: dict[Path, FileIdentity], control: OperationControl
) -> None:
    for path, original in paths.items():
        control.checkpoint()
        if path.resolve(strict=True) != path or file_identity(path.lstat()) != original:
            raise EvidenceIntegrityError(
                "Original readonly Map input changed during staging"
            )
