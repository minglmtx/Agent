"""Private, worker-local artifact scope; descriptors confer no restore authority."""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import field_validator, model_validator
from lab_generate_skill.domain.validation import Contract, Identifier, Sha256

ARTIFACT_PATHS = frozenset(
    {
        "pub/media/catalog/product",
        "pub/media/tmp/catalog/product",
        "pub/media/wysiwyg",
        "pub/media/.thumbs",
        "var/export",
        "var/training-mail",
        "pub/media/training-assets",
    }
)


class AdminArtifactLayout(Contract):
    schema_version: Literal["admin-artifact-layout/1"] = "admin-artifact-layout/1"
    instance_id: Identifier
    node_root: str
    app_root: str
    backup_root: str
    paths: tuple[str, ...]

    @field_validator("node_root", "app_root", "backup_root")
    @classmethod
    def absolute_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not path.is_absolute()
            or value == "/"
            or str(path) != value
            or ".." in path.parts
            or "\0" in value
        ):
            raise ValueError("Artifact roots must be canonical absolute paths")
        return value

    @field_validator("paths")
    @classmethod
    def selected_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if (
            not value
            or len(set(value)) != len(value)
            or not set(value) <= ARTIFACT_PATHS
        ):
            raise ValueError("Declare distinct supported artifact paths")
        return value

    @model_validator(mode="after")
    def separate_roots(self) -> Self:
        root, app, backup = map(
            PurePosixPath, (self.node_root, self.app_root, self.backup_root)
        )
        if (
            app == root
            or backup == root
            or not app.is_relative_to(root)
            or not backup.is_relative_to(root)
        ):
            raise ValueError("Artifact roots must belong to the declared node root")
        if app.is_relative_to(backup) or backup.is_relative_to(app):
            raise ValueError("Backup and application trees must be disjoint")
        return self


class AdminArtifactSnapshot(Contract):
    schema_version: Literal["admin-artifact-snapshot/1"] = "admin-artifact-snapshot/1"
    layout: AdminArtifactLayout
    # Ordered exactly as layout.paths. None is absence, not an empty directory.
    tree_sha256: tuple[Sha256 | None, ...]

    @model_validator(mode="after")
    def complete(self) -> Self:
        if len(self.tree_sha256) != len(self.layout.paths):
            raise ValueError("Every selected path needs its original tree identity")
        return self
