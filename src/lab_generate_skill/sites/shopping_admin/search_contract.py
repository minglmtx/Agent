"""Original private Elasticsearch snapshot identity, not a whole-site ResetReceipt."""

from typing import Literal, Self
from pydantic import Field, field_validator, model_validator
from lab_generate_skill.domain.validation import Contract
from .service_contract import AdminServiceSpec


class AdminSearchSnapshot(Contract):
    schema_version: Literal["admin-search-snapshot/1"] = "admin-search-snapshot/1"
    service: AdminServiceSpec
    cluster_uuid: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    version: str = Field(pattern=r"^7\.[0-9]+\.[0-9]+$")
    repository: Literal["lab_admin_recovery"] = "lab_admin_recovery"
    snapshot: Literal["baseline"] = "baseline"
    snapshot_uuid: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    indices: tuple[str, ...] = Field(max_length=256)
    data_streams: tuple[str, ...] = Field(max_length=256)
    shards: int = Field(ge=0)

    @field_validator("indices", "data_streams")
    @classmethod
    def exact_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        import re

        if tuple(sorted(set(value))) != value or any(
            not re.fullmatch(r"[a-z0-9.][a-z0-9_.-]{0,254}", n) or n in (".", "..")
            for n in value
        ):
            raise ValueError("Expected sorted distinct literal index names")
        return value


class AdminSearchRestored(Contract):
    schema_version: Literal["admin-search-restored/1"] = "admin-search-restored/1"
    original: AdminSearchSnapshot
    restored_indices: tuple[str, ...]
    restored_data_streams: tuple[str, ...]
    successful_shards: int = Field(ge=0)
    health: Literal["green", "yellow"]

    @model_validator(mode="after")
    def complete(self) -> Self:
        if (
            self.restored_indices != self.original.indices
            or self.restored_data_streams != self.original.data_streams
            or self.successful_shards != self.original.shards
        ):
            raise ValueError("Restore must confirm all original indices and shards")
        return self
