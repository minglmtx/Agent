"""Worker-local Admin DB snapshot descriptors; not site or restore admission."""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, field_validator, model_validator
from lab_generate_skill.domain.validation import Contract, Identifier, Sha256


class AdminDatabaseLayout(Contract):
    schema_version: Literal["admin-database-layout/1"] = "admin-database-layout/1"
    instance_id: Identifier
    node_root: str
    state_root: str
    image_path: str
    image_sha256: Sha256
    apptainer: str

    @field_validator("node_root", "state_root", "image_path", "apptainer")
    @classmethod
    def canonical_path(cls, value: str) -> str:
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
    def local_resources(self) -> Self:
        root, state, image = map(
            PurePosixPath, (self.node_root, self.state_root, self.image_path)
        )
        if (
            state == root
            or not state.is_relative_to(root)
            or not image.is_relative_to(root)
        ):
            raise ValueError(
                "DB state and staged image must belong to the declared node root"
            )
        if image == state or image.is_relative_to(state):
            raise ValueError(
                "Staged read-only image must stay outside mutable DB state"
            )
        return self


class AdminDatabaseSnapshot(Contract):
    schema_version: Literal["admin-database-snapshot/1"] = "admin-database-snapshot/1"
    layout: AdminDatabaseLayout
    size_bytes: int = Field(ge=100)
    sha256: Sha256


class DatabaseReply(Contract):
    schema_version: Literal["admin-database-reply/2"] = "admin-database-reply/2"
    operation: Literal["save", "verify", "restore"]
    size_bytes: int = Field(ge=100)
    sha256: Sha256


class DatabaseReplyError(ValueError):
    def __init__(self, raw_reply: bytes) -> None:
        self.raw_reply = raw_reply
        super().__init__(
            "Invalid native database reply; retain original state and inspect"
        )
