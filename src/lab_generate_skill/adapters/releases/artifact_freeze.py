"""Worker-local immutable artifact publication to a new trusted workspace root.

Source is an explicit complete file pin, not a directory discovery policy.
No overwrite, symlink materialization, download, current switch, or implicit
cleanup/retry. Failures retain the destination and attach artifact_freeze facts;
caller must supervise I/O and retain publisher ownership until termination.
"""

from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.validation import Identifier
from lab_generate_skill.ports.lifecycle import OperationControl
from .artifact_copy import copy_pinned_file, sync_directory, sync_regular_file
from .files import _inventory, verify_artifact


@dataclass(frozen=True)
class ArtifactFreezeObservation:
    artifact: ReleaseArtifact
    destination_created: bool


class FileArtifactFreezer:
    def __init__(self, workspace_root: Path, publication_root: Path) -> None:
        if (
            not isinstance(workspace_root, Path)
            or not isinstance(publication_root, Path)
            or not workspace_root.is_absolute()
            or not publication_root.is_absolute()
        ):
            raise ValueError("Trusted artifact roots must be absolute Paths")
        if publication_root == workspace_root or not publication_root.is_relative_to(
            workspace_root
        ):
            raise ValueError("Publication root must be a workspace subdirectory")
        self.workspace_root, self.publication_root = workspace_root, publication_root

    def _durable(self, artifact: ReleaseArtifact, control: OperationControl) -> None:
        root = Path(artifact.root)
        directories = {root}
        for entry in artifact.files:
            control.checkpoint()
            path = root / entry.path
            sync_regular_file(path)
            directories.update(
                parent
                for parent in path.parents
                if parent == root or parent.is_relative_to(root)
            )
        for directory in sorted(
            directories, key=lambda path: len(path.parts), reverse=True
        ):
            control.checkpoint()
            sync_directory(directory)
        sync_directory(self.publication_root)

    def freeze(
        self, source: ReleaseArtifact, artifact_id: str, control: OperationControl
    ) -> ReleaseArtifact:
        source = ReleaseArtifact.model_validate(source)
        artifact_id = TypeAdapter(Identifier).validate_python(artifact_id, strict=True)
        control.checkpoint()
        source_root = Path(source.root)
        for root in (self.workspace_root, self.publication_root, source_root):
            if root.resolve(strict=True) != root or not root.is_dir():
                raise EvidenceIntegrityError(
                    "Artifact roots must be existing canonical directories"
                )
        if source_root == self.workspace_root or not source_root.is_relative_to(
            self.workspace_root
        ):
            raise EvidenceIntegrityError("Source must be a workspace subdirectory")
        target = self.publication_root / artifact_id
        if (
            target == source_root
            or target.is_relative_to(source_root)
            or source_root.is_relative_to(target)
        ):
            raise ValueError("Source and destination cannot overlap")
        artifact = ReleaseArtifact(
            artifact_id=artifact_id, root=str(target), files=source.files
        )
        created = False
        try:
            try:
                target.lstat()
            except FileNotFoundError:
                pass
            else:
                verify_artifact(artifact, control)
                self._durable(artifact, control)
                control.checkpoint()
                return artifact
            before = _inventory(source_root, control, require_readonly=False)
            if set(before) != {entry.path for entry in source.files}:
                raise EvidenceIntegrityError(
                    "Source file set differs from explicit pin"
                )
            control.checkpoint()
            target.mkdir(mode=0o700)
            created = True
            sync_directory(self.publication_root)
            directories = {target}
            for entry in source.files:
                control.checkpoint()
                directory = (target / entry.path).parent
                directory.mkdir(parents=True, exist_ok=True)
                directories.add(directory)
                directories.update(
                    parent
                    for parent in directory.parents
                    if parent == target or parent.is_relative_to(target)
                )
                copy_pinned_file(source_root, target, entry, control)
            if _inventory(source_root, control, require_readonly=False) != before:
                raise EvidenceIntegrityError(
                    "Source file inventory changed during freeze"
                )
            for directory in sorted(
                directories, key=lambda path: len(path.parts), reverse=True
            ):
                control.checkpoint()
                directory.chmod(0o555)
                sync_directory(directory)
            verify_artifact(artifact, control)
            sync_directory(self.publication_root)
            control.checkpoint()
            return artifact
        except BaseException as error:
            setattr(
                error, "artifact_freeze", ArtifactFreezeObservation(artifact, created)
            )
            raise
