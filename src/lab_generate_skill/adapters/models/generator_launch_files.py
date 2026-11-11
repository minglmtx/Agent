"""Check the frozen launch files without importing the child installation.

Code has an exact inventory. Python roles may pin selected files in a shared
read-only installation; undeclared neighbours are not claimed as verified.
Actual loaded origins still require the isolated worker's own handshake.
"""

import os
from pathlib import Path
import stat

from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.files import _file, verify_artifact


def verify_launch_files(
    manifest: ReleaseManifest,
    workspace: Path,
    executable: str,
    control: OperationControl,
) -> None:
    manifest = ReleaseManifest.model_validate(manifest)
    if not isinstance(workspace, Path) or not workspace.is_absolute():
        raise ValueError("Launch workspace must be an absolute Path")
    if workspace.resolve(strict=True) != workspace or not workspace.is_dir():
        raise EvidenceIntegrityError("Launch workspace is not canonical")
    components = {c.component_id: c for c in manifest.components}
    artifacts = {a.artifact_id: a for a in manifest.artifacts}
    found = False
    for role in ("code", "python"):
        selected = next(
            r for r in manifest.roles if (r.role, r.scope_id) == (role, "global")
        )
        for key in components[selected.component_id].artifact_ids:
            artifact = artifacts[key]
            root = Path(artifact.root)
            control.checkpoint()
            if (
                root == workspace
                or not root.is_relative_to(workspace)
                or (
                    root.resolve(strict=True) != root
                    or not root.is_dir()
                    or root.stat().st_mode & 0o222
                )
            ):
                raise EvidenceIntegrityError(
                    "Launch artifact is not frozen in workspace"
                )
            if role == "code":
                verify_artifact(artifact, control)
            else:
                for entry in artifact.files:
                    _file(root, entry, control)
                    if str(root / entry.path) == executable:
                        if not entry.executable:
                            raise EvidenceIntegrityError(
                                "Pinned Python is not executable"
                            )
                        found = True
    if not found:
        raise EvidenceIntegrityError("Launch Python is not in the frozen Python role")
    control.checkpoint()


def verify_system_command(path: str, control: OperationControl) -> None:
    """Root-owned canonical scheduler command; no user-writable path component."""
    command = Path(path)
    control.checkpoint()
    if not command.is_absolute() or command.resolve(strict=True) != command:
        raise EvidenceIntegrityError("Scheduler executable is not canonical")
    for part in (command, *command.parents):
        control.checkpoint()
        value = part.lstat()
        if (
            value.st_uid != 0
            or value.st_gid != 0
            or value.st_mode & 0o022
            or os.access(part, os.W_OK)
        ):
            raise EvidenceIntegrityError("Scheduler path is writable or not root-owned")
        if part == command:
            if not stat.S_ISREG(value.st_mode) or not os.access(part, os.X_OK):
                raise EvidenceIntegrityError("Scheduler command is not executable")
        elif not stat.S_ISDIR(value.st_mode):
            raise EvidenceIntegrityError("Scheduler parent is not a directory")
    control.checkpoint()
