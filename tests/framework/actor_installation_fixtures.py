"""Explicit installation declarations for unit and actual-child engineering tests.

The unit receipt is synthetic and is never wired into the installed bootstrap.
The installed declaration pins the actual isolated wheel/Python fixture.
"""

from pathlib import Path
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.release_installation import InstalledReleaseModule
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
)
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.ports.lifecycle import OperationControl
from generator_release_fixtures import metadata
from installed_source_fixtures import InstalledFixture
from release_fixtures import manifest


def declaration(
    release: ReleaseManifest, workspace: Path, python: Path
) -> ReleaseInstallation:
    return ReleaseInstallation(
        manifest_ref=evidence_reference(
            release.model_dump_json().encode(), metadata("release-manifest/1")
        ),
        manifest=release,
        workspace_root=str(workspace),
        python_executable=str(python),
    )


def installed_declaration(fixture: InstalledFixture) -> ReleaseInstallation:
    return declaration(fixture.manifest, fixture.workspace, fixture.executable)


def unit_declaration() -> ReleaseInstallation:
    return declaration(
        manifest(Path("/unit/site")), Path("/unit"), Path("/unit-worker")
    )


def unit_verifier(
    installation: ReleaseInstallation, control: OperationControl
) -> InstalledReleaseSources:
    control.checkpoint()
    return InstalledReleaseSources(
        release_id=installation.manifest.release_id,
        manifest_sha256=installation.manifest_ref.sha256,
        executable=installation.python_executable,
        package_root="/unit/site/lab_generate_skill",
        distribution_version="0.1.0",
        modules=(
            InstalledReleaseModule(
                name="lab_generate_skill",
                filename="/unit/site/lab_generate_skill/__init__.py",
            ),
        ),
    )
