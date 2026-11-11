"""Trusted-root adapter for the existing complete frozen-file verifier."""

from pathlib import Path
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.ports.lifecycle import OperationControl
from .files import verify_release_files


class FrozenReleaseFiles:
    def __init__(self, workspace_root: Path) -> None:
        if not isinstance(workspace_root, Path) or not workspace_root.is_absolute():
            raise ValueError("Trusted workspace root must be absolute")
        self._root = workspace_root

    def verify(self, manifest: ReleaseManifest, control: OperationControl) -> None:
        verify_release_files(manifest, self._root, control)
