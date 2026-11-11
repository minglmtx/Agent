"""Pure check of an installed-source reply against the original storage release.

Actual file/interpreter verification happens in the guarded child. A matching
envelope alone is not authority to launch or to recover another controller.
"""

from pathlib import PurePosixPath
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.release_installation import InstalledReleaseSources


def check_storage_installation(
    config: EvidenceStorageConfig,
    observed: InstalledReleaseSources | None,
    *,
    entry_module: str,
    required: bool,
) -> None:
    if observed is None:
        if required:
            raise ValueError("Storage success requires observed installed sources")
        return
    observed = InstalledReleaseSources.model_validate(observed)
    declaration = config.installation
    if (observed.release_id, observed.manifest_sha256, observed.executable) != (
        declaration.manifest.release_id,
        declaration.manifest_ref.sha256,
        declaration.python_executable,
    ):
        raise ValueError("Storage reply differs from original installed release")
    manifest = declaration.manifest
    code_id = next(
        r.component_id
        for r in manifest.roles
        if (r.role, r.scope_id) == ("code", "global")
    )
    code = next(c for c in manifest.components if c.component_id == code_id)
    paths = {
        str(PurePosixPath(a.root) / f.path)
        for a in manifest.artifacts
        if a.artifact_id in code.artifact_ids
        for f in a.files
    }
    if not any(m.name == entry_module for m in observed.modules) or any(
        m.filename not in paths for m in observed.modules
    ):
        raise ValueError("Storage observed modules differ from original code inventory")
