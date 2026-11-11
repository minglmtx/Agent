"""Strict native reply; no default success or opaque payload dictionaries."""

from typing import Literal
from pydantic import Field
from lab_generate_skill.domain.validation import Contract


class SearchSnapshotIdentity(Contract):
    cluster_uuid: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    version: str = Field(pattern=r"^7\.[0-9]+\.[0-9]+$")
    repository: Literal["lab_admin_recovery"]
    snapshot: Literal["baseline"]
    snapshot_uuid: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    indices: tuple[str, ...]
    data_streams: tuple[str, ...]
    shards: int = Field(ge=0)


class SearchReply(Contract):
    schema_version: Literal["admin-search-reply/2"]
    operation: Literal["save", "verify", "preflight", "restore"]
    snapshot: SearchSnapshotIdentity
    health: Literal["green", "yellow"] | None = None
    successful_shards: int | None = Field(default=None, ge=0)
