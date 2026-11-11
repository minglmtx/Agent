"""Immutable physical storage configuration; declarations are not admission."""

import hashlib
from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from .evidence_sessions import EvidenceSessionCapacity
from .validation import Contract, Identifier
from .release_installation import ReleaseInstallation


class EvidenceStorageConfig(Contract):
    schema_version: Literal["evidence-storage-config/2"] = "evidence-storage-config/2"
    storage_id: Identifier
    evidence_root: str = Field(min_length=1, max_length=4096)
    session_root: str = Field(min_length=1, max_length=4096)
    max_object_bytes: int = Field(ge=1, le=64 * 1024 * 1024)
    capacity: EvidenceSessionCapacity
    installation: ReleaseInstallation

    @model_validator(mode="after")
    def paths(self) -> Self:
        roots = [PurePosixPath(v) for v in (self.evidence_root, self.session_root)]
        for value, root in zip((self.evidence_root, self.session_root), roots):
            if (
                not root.is_absolute()
                or str(root) != value
                or ".." in root.parts
                or "\0" in value
                or "\\" in value
            ):
                raise ValueError("Storage roots must be canonical absolute POSIX paths")
        if roots[0].is_relative_to(roots[1]) or roots[1].is_relative_to(roots[0]):
            raise ValueError("Evidence and session roots must be disjoint")
        return self

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()
