"""Pinned workspace image and predeclared private node paths, without I/O.

This plan identifies one acquisition's files; it is not permission to create,
remove or recover them. Outer resource intent must persist it before staging.
"""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import field_validator, model_validator
from .release import ReleaseFile
from .validation import Contract, Identifier


class SiteFilesPlan(Contract):
    schema_version: Literal["site-files-plan/1"] = "site-files-plan/1"
    instance_id: Identifier
    workspace_root: str
    source_path: str
    node_root: str
    image: ReleaseFile

    @field_validator("workspace_root", "source_path", "node_root")
    @classmethod
    def canonical(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not path.is_absolute()
            or value == "/"
            or str(path) != value
            or ".." in path.parts
            or any(c in value for c in (":", ",", "\0", "\n", "\r"))
        ):
            raise ValueError("Expected canonical absolute path without bind delimiters")
        return value

    @model_validator(mode="after")
    def scope(self) -> Self:
        workspace, source, node = map(
            PurePosixPath, (self.workspace_root, self.source_path, self.node_root)
        )
        if source == workspace or not source.is_relative_to(workspace):
            raise ValueError("Image must be inside the declared workspace")
        if (
            node == PurePosixPath("/tmp")
            or not node.is_relative_to("/tmp")
            or node.is_relative_to(workspace)
            or workspace.is_relative_to(node)
        ):
            raise ValueError(
                "Private node root must be under /tmp and separate from workspace"
            )
        if (
            self.image.path != source.name
            or self.image.executable
            or self.image.size_bytes <= 0
        ):
            raise ValueError(
                "Expected nonempty nonexecutable image pin for the exact source basename"
            )
        return self

    @property
    def image_path(self) -> str:
        return str(PurePosixPath(self.node_root) / "image" / self.image.path)

    @property
    def state_root(self) -> str:
        return str(PurePosixPath(self.node_root) / "state")

    @property
    def log_root(self) -> str:
        return str(PurePosixPath(self.node_root) / "logs")
