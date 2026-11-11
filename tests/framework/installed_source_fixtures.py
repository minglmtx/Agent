"""Freeze an isolated test installation, never the published workspace runtime."""

import hashlib
import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from lab_generate_skill.domain.release import (
    ReleaseArtifact,
    ReleaseFile,
    ReleaseManifest,
)
from release_fixtures import manifest as base_manifest
from worker_install_fixtures import installed_worker as installed_worker


@dataclass(frozen=True)
class InstalledFixture:
    executable: Path
    workspace: Path
    manifest: ReleaseManifest


@pytest.fixture(scope="session")
def installed_sources(installed_worker: Path) -> Iterator[InstalledFixture]:
    runtime = installed_worker.parent.parent
    workspace = runtime.parent
    executable = runtime / "bin" / "verified-python"
    shutil.copyfile(sys.executable, executable)
    executable.chmod(0o555)
    target = (
        runtime
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    paths = [target, *target.rglob("*")]
    modes = {path: path.stat().st_mode & 0o777 for path in paths}
    modes[executable.parent] = executable.parent.stat().st_mode & 0o777
    try:
        entries = []
        for path in paths:
            assert not path.is_symlink()
            if path.is_file():
                path.chmod(0o444)
                raw = path.read_bytes()
                entries.append(
                    ReleaseFile(
                        path=str(path.relative_to(target)),
                        sha256=hashlib.sha256(raw).hexdigest(),
                        size_bytes=len(raw),
                        executable=False,
                    )
                )
        for path in paths:
            if path.is_dir():
                path.chmod(0o555)
        executable.parent.chmod(0o555)
        code = ReleaseArtifact(
            artifact_id="files",
            root=str(target),
            files=tuple(sorted(entries, key=lambda item: item.path)),
        )
        raw = executable.read_bytes()
        python = ReleaseArtifact(
            artifact_id="python-files",
            root=str(executable.parent),
            files=(
                ReleaseFile(
                    path=executable.name,
                    sha256=hashlib.sha256(raw).hexdigest(),
                    size_bytes=len(raw),
                    executable=True,
                ),
            ),
        )
        base = base_manifest(target)
        components = tuple(
            (
                c.model_copy(update={"artifact_ids": ("python-files",)})
                if c.component_id == "python"
                else c
            )
            for c in base.components
        )
        manifest = ReleaseManifest.model_validate(
            {**base.model_dump(), "artifacts": (code, python), "components": components}
        )
        yield InstalledFixture(executable, workspace, manifest)
    finally:
        for path, mode in modes.items():
            path.chmod(mode)
        executable.unlink(missing_ok=True)
