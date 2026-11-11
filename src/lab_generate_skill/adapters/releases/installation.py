"""Verify one declared release against the actual isolated installed process.

Caller must run this inside external supervision before component effects.
No storage/model role imports, dynamic code loading, runtime repair or authority.
"""

import sys
from pathlib import Path
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
    InstalledReleaseModule,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from .installed_sources import verify_installed_sources


def verify_release_installation(
    installation: ReleaseInstallation, control: OperationControl
) -> InstalledReleaseSources:
    installation = ReleaseInstallation.model_validate(installation)
    control.checkpoint()
    if sys.executable != installation.python_executable:
        raise EvidenceIntegrityError("Actual Python differs from declared launch")
    actual = verify_installed_sources(
        installation.manifest, Path(installation.workspace_root), control
    )
    if (actual.release_id, actual.manifest_sha256, actual.executable) != (
        installation.manifest.release_id,
        installation.manifest_ref.sha256,
        installation.python_executable,
    ):
        raise EvidenceIntegrityError(
            "Observed installation differs from frozen release"
        )
    result = InstalledReleaseSources(
        release_id=actual.release_id,
        manifest_sha256=actual.manifest_sha256,
        executable=actual.executable,
        package_root=actual.package_root,
        distribution_version=actual.distribution_version,
        modules=tuple(
            InstalledReleaseModule(name=m.name, filename=m.filename)
            for m in actual.modules
        ),
    )
    control.checkpoint()
    return result
