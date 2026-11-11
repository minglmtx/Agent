"""Shared release installation fields and observed source projection, not rights.

The workspace root and executable come from trusted launch assembly. The child
must inspect its actual interpreter and loaded modules; these envelopes alone
do not prove execution or permit a launch. No dynamic module names are inputs.
"""

import hashlib
from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from .evidence import EvidenceRef
from .release import ReleaseManifest
from .state_scope import private_state_ref
from .validation import Contract, Identifier, NonEmptyText, Sha256


def _absolute(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not path.is_absolute()
        or str(path) != value
        or ".." in path.parts
        or "\0" in value
        or "\\" in value
    ):
        raise ValueError("Installation paths must be canonical absolute POSIX paths")


class InstallationDeclaration(Contract):
    """Shared validated fields; concrete wire contracts fix schema_version."""

    schema_version: str
    manifest_ref: EvidenceRef
    manifest: ReleaseManifest
    workspace_root: str = Field(min_length=1, max_length=4096)
    python_executable: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def exact_manifest(self) -> Self:
        private_state_ref(self.manifest_ref, "release-manifest/1")
        _absolute(self.workspace_root)
        _absolute(self.python_executable)
        raw = self.manifest.model_dump_json().encode()
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (
            self.manifest_ref.size_bytes,
            self.manifest_ref.sha256,
        ):
            raise ValueError(
                "Installation must carry the exact canonical release manifest"
            )
        if len(self.model_dump_json().encode()) > 12 * 1024 * 1024:
            raise ValueError("Installation declaration exceeds worker byte budget")
        return self


class InstalledReleaseModule(Contract):
    name: str = Field(
        pattern=r"^lab_generate_skill(?:\.[A-Za-z_][A-Za-z0-9_]*)*$", max_length=1024
    )
    filename: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def source_path(self) -> Self:
        _absolute(self.filename)
        suffix = self.name.replace(".", "/")
        if not (
            self.filename.endswith("/" + suffix + ".py")
            or self.filename.endswith("/" + suffix + "/__init__.py")
        ):
            raise ValueError("Installed module name differs from source filename")
        return self


class InstalledSourceProjection(Contract):
    """Shared observed fields; concrete wire contracts fix schema_version."""

    schema_version: str
    release_id: Identifier
    manifest_sha256: Sha256
    executable: str = Field(min_length=1, max_length=4096)
    package_root: str = Field(min_length=1, max_length=4096)
    distribution_version: NonEmptyText = Field(max_length=256)
    modules: tuple[InstalledReleaseModule, ...] = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def complete_projection(self) -> Self:
        _absolute(self.executable)
        _absolute(self.package_root)
        names = [m.name for m in self.modules]
        if names != sorted(set(names)) or "lab_generate_skill" not in names:
            raise ValueError(
                "Installed module projection must be unique, sorted and include package"
            )
        root = PurePosixPath(self.package_root)
        if any(
            not PurePosixPath(m.filename).is_relative_to(root) for m in self.modules
        ):
            raise ValueError("Installed module is outside the observed package root")
        if len(self.model_dump_json().encode()) > 4 * 1024 * 1024:
            raise ValueError("Installed module projection exceeds byte budget")
        return self


class ReleaseInstallation(InstallationDeclaration):
    schema_version: Literal["release-installation/1"] = "release-installation/1"


class InstalledReleaseSources(InstalledSourceProjection):
    schema_version: Literal["installed-release-sources/1"] = (
        "installed-release-sources/1"
    )
