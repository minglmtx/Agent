"""Check current isolated interpreter and already-loaded installed project sources.

Run inside an externally supervised worker against a trusted frozen release.
This checks the actual executable, all declared project files and loaded origins,
not all third-party/native
dependencies, executed in-memory bytecode, permission, or future plugin imports.
No sys.path changes, installation, imports of plugins, or automatic repair.
"""

import hashlib
import importlib.metadata
import sys
from dataclasses import dataclass
from pathlib import Path

from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseManifest, ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from .files import _inventory
from .installed_files import InstalledFileTraversal
from .module_origins import ModuleOrigin, observe_project_modules


@dataclass(frozen=True)
class InstalledSources:
    release_id: str
    manifest_sha256: str
    executable: str
    package_root: str
    distribution_version: str
    modules: tuple[ModuleOrigin, ...]


def verify_installed_sources(
    manifest: ReleaseManifest, workspace_root: Path, control: OperationControl
) -> InstalledSources:
    manifest = ReleaseManifest.model_validate(manifest)
    control.checkpoint()
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise EvidenceIntegrityError("Installed source verification requires -I -B")
    if not isinstance(workspace_root, Path) or not workspace_root.is_absolute():
        raise ValueError("Trusted workspace root must be absolute")
    if (
        workspace_root.resolve(strict=True) != workspace_root
        or not workspace_root.is_dir()
    ):
        raise EvidenceIntegrityError("Workspace must be a canonical directory")
    components = {c.component_id: c for c in manifest.components}
    artifacts = {a.artifact_id: a for a in manifest.artifacts}
    roles: dict[tuple[str, str], str] = {
        (r.role, r.scope_id): r.component_id for r in manifest.roles
    }

    def entries(role: str) -> dict[Path, tuple[Path, ReleaseFile]]:
        found: dict[Path, tuple[Path, ReleaseFile]] = {}
        component = components[roles[(role, "global")]]
        for aid in component.artifact_ids:
            artifact = artifacts[aid]
            root = Path(artifact.root)
            if (
                root == workspace_root
                or not root.is_relative_to(workspace_root)
                or root.resolve(strict=True) != root
                or not root.is_dir()
                or root.stat().st_mode & 0o222
            ):
                raise EvidenceIntegrityError(
                    "Installed artifact root is not frozen in workspace"
                )
            for entry in artifact.files:
                found[root / entry.path] = (root, entry)
        return found

    code = entries("code")
    python = entries("python")

    with InstalledFileTraversal({**code, **python}, control) as traversal:

        def verify(path: Path, bound: dict[Path, tuple[Path, ReleaseFile]]) -> None:
            control.checkpoint()
            if not path.is_absolute() or path not in bound:
                raise EvidenceIntegrityError(
                    "Loaded file is outside its release role: " + str(path)
                )
            traversal.verify(path)

        executable = Path(sys.executable)
        verify(executable, python)
        if not python[executable][1].executable:
            raise EvidenceIntegrityError(
                "Python executable must retain its executable mode"
            )
        before = observe_project_modules()
        package_root = Path(
            next(m.filename for m in before if m.name == "lab_generate_skill")
        ).parent
        package_inventory = _inventory(package_root, control)
        expected = {
            str(path.relative_to(package_root))
            for path in code
            if path.is_relative_to(package_root)
        }
        if set(package_inventory) != expected or any(
            name.endswith((".pyc", ".pyo")) for name in package_inventory
        ):
            raise EvidenceIntegrityError(
                "Installed project inventory differs or contains bytecode cache"
            )
        distribution = importlib.metadata.distribution("lab-generate-skill")
        if Path(str(distribution.locate_file("lab_generate_skill"))) != package_root:
            raise EvidenceIntegrityError(
                "Installed metadata points to another project tree"
            )
        metadata_files = tuple(distribution.files or ())
        metadata_dirs = {
            str(item.parent)
            for item in metadata_files
            if str(item).endswith(".dist-info/METADATA")
        }
        if len(metadata_dirs) != 1:
            raise EvidenceIntegrityError(
                "Project must have one pinned wheel dist-info directory"
            )
        directory = next(iter(metadata_dirs))
        for name in ("METADATA", "WHEEL", "RECORD"):
            path = Path(str(distribution.locate_file(directory + "/" + name)))
            verify(path, code)
        # A package inventory match alone does not verify not-yet-imported code.
        for path in code:
            verify(path, code)
        for module in before:
            path = Path(module.filename)
            if not path.is_relative_to(package_root):
                raise EvidenceIntegrityError(
                    "Loaded module is outside installed package root"
                )
            control.checkpoint()
            if not path.is_absolute() or path not in code:
                raise EvidenceIntegrityError(
                    "Loaded file is outside its release role: " + str(path)
                )
            # Every declared code file was fully hashed above. Package files
            # also retain the independent before/after inventory comparison,
            # so a loaded file needs no second hash within this verification.
            # Metadata outside the package and the executable retain their
            # existing explicit checks; every later call hashes all code again.
        if (
            observe_project_modules() != before
            or _inventory(package_root, control) != package_inventory
        ):
            raise EvidenceIntegrityError(
                "Loaded project origins or files changed during verification"
            )
        control.checkpoint()
        return InstalledSources(
            manifest.release_id,
            hashlib.sha256(manifest.model_dump_json().encode()).hexdigest(),
            str(executable),
            str(package_root),
            distribution.version,
            before,
        )
