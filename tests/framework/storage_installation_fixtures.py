"""Explicit synthetic wire declarations or the actual frozen installed fixture."""

from pathlib import Path
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
    InstalledReleaseModule,
)
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.release import ReleaseManifest, ReleaseFile
from generator_installation_fixtures import unit_declaration, installed_declaration
from generator_release_fixtures import metadata
from installed_source_fixtures import InstalledFixture


def storage_installation(
    fixture: InstalledFixture | None = None, *, python: Path = Path("/trusted/python")
) -> ReleaseInstallation:
    if fixture is not None:
        original = installed_declaration(fixture)
        return ReleaseInstallation.model_validate(
            {**original.model_dump(), "schema_version": "release-installation/1"}
        )
    original = unit_declaration()
    data = original.manifest.model_dump()
    files = tuple(
        ReleaseFile(
            path=name, sha256="0" * 64, size_bytes=0, executable=False
        ).model_dump()
        for name in (
            "lab_generate_skill/__init__.py",
            "lab_generate_skill/bootstrap/evidence_worker.py",
            "lab_generate_skill/bootstrap/evidence_resolver.py",
        )
    )
    data["artifacts"][0]["files"] = tuple(
        sorted((*data["artifacts"][0]["files"], *files), key=lambda item: item["path"])
    )
    manifest = ReleaseManifest.model_validate(data)
    return ReleaseInstallation(
        manifest=manifest,
        manifest_ref=evidence_reference(
            manifest.model_dump_json().encode(), metadata("release-manifest/1")
        ),
        workspace_root=original.workspace_root,
        python_executable=str(python),
    )


def unit_storage_sources(installation: ReleaseInstallation) -> InstalledReleaseSources:
    root = installation.manifest.artifacts[0].root + "/lab_generate_skill"
    return InstalledReleaseSources(
        release_id=installation.manifest.release_id,
        manifest_sha256=installation.manifest_ref.sha256,
        executable=installation.python_executable,
        package_root=root,
        distribution_version="0.1.0",
        modules=tuple(
            InstalledReleaseModule(name=name, filename=root + suffix)
            for name, suffix in (
                ("lab_generate_skill", "/__init__.py"),
                (
                    "lab_generate_skill.bootstrap.evidence_resolver",
                    "/bootstrap/evidence_resolver.py",
                ),
                (
                    "lab_generate_skill.bootstrap.evidence_worker",
                    "/bootstrap/evidence_worker.py",
                ),
            )
        ),
    )
