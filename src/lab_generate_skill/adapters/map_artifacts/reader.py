"""Independent original-plan readback of full immutable files, never a CAS chunk API."""

import hashlib
import os
from pathlib import Path
import stat
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.map_private_artifact import (
    MapArtifactPlan,
    parse_map_artifact_plan,
    MapArtifactHandle,
    MapArtifactManifest,
)
from lab_generate_skill.ports.map_private_artifact import MapArtifactAuthority
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.artifact_copy import close_all
from lab_generate_skill.adapters.releases.files import verify_artifact
from .files import private_directory
from lab_generate_skill.adapters.releases.file_read import frozen_bytes as frozen_bytes


class MapArtifactReader:
    def __init__(
        self,
        plan: MapArtifactPlan,
        workspace: Path,
        authority: MapArtifactAuthority,
    ) -> None:
        self.plan = parse_map_artifact_plan(plan)
        if (
            not isinstance(workspace, Path)
            or str(workspace) != self.plan.workspace_root
            or not callable(getattr(authority, "verify", None))
        ):
            raise ValueError("Trusted workspace and original read authority required")
        self.workspace, self.authority = workspace, authority

    def manifest(
        self, handle: MapArtifactHandle, control: OperationControl
    ) -> MapArtifactManifest:
        handle = MapArtifactHandle.model_validate(handle)
        if handle.plan_sha256 != self.plan.digest:
            raise EvidenceIntegrityError(
                "Private artifact handle changed original plan"
            )
        self.authority.verify(self.plan, "read", control)
        if self.workspace.resolve(strict=True) != self.workspace:
            raise EvidenceIntegrityError("Trusted workspace changed")
        root = Path(self.plan.private_root)
        private_directory(root)
        published = root / "published"
        if (
            published.resolve(strict=True) != published
            or not published.is_dir()
            or published.stat().st_mode & 0o222
        ):
            raise EvidenceIntegrityError(
                "Original publication directory is not immutable"
            )
        raw = frozen_bytes(published, handle.manifest, control)
        manifest = MapArtifactManifest.model_validate_json(raw)
        if manifest.plan != self.plan or manifest.model_dump_json().encode() != raw:
            raise EvidenceIntegrityError(
                "Manifest changed original plan or canonical record"
            )
        verify_artifact(manifest.artifact, control)
        self.authority.verify(self.plan, "read", control)
        return manifest

    def read(
        self, handle: MapArtifactHandle, name: str, control: OperationControl
    ) -> bytes:
        if not isinstance(name, str):
            raise ValueError("Explicit retained filename required")
        manifest = self.manifest(handle, control)
        entry = next((e for e in manifest.artifact.files if e.path == name), None)
        if entry is None:
            raise EvidenceIntegrityError("File not in original immutable manifest")
        data = frozen_bytes(Path(manifest.artifact.root), entry, control)
        self.authority.verify(self.plan, "read", control)
        return data
