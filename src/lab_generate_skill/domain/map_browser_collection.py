"""Selected original source inputs and terminal full-file handle, no task verdict."""

import hashlib
from typing import Literal, Self
from urllib.parse import urlsplit
from pydantic import Field, field_validator, model_validator
from .validation import Contract, Sha256
from .lifecycle import OperationContext
from .release import ReleaseArtifact, ReleaseFile
from .map_private_artifact import MapPrivateArtifactPlan, MapArtifactHandle

SOURCE_PATHS = frozenset(
    {
        "app/assets/javascripts/index.js",
        "app/assets/javascripts/leaflet.share.js",
        "app/assets/javascripts/leaflet.layers.js",
        "vendor/assets/leaflet/leaflet.osm.js",
    }
)


class MapBrowserCollectionSpec(Contract):
    schema_version: Literal["map-browser-collection-spec/2"] = (
        "map-browser-collection-spec/2"
    )
    operation: OperationContext
    lifetime_operation: OperationContext
    original_sources: ReleaseArtifact
    tile_origin: str
    max_requests: int = Field(ge=1, le=256)

    @field_validator("tile_origin")
    @classmethod
    def literal_origin(cls, value: str) -> str:
        u = urlsplit(value)
        if (
            u.scheme != "http"
            or u.hostname != "127.0.0.1"
            or u.port is None
            or not 1 <= u.port <= 65535
            or value != f"http://127.0.0.1:{u.port}"
        ):
            raise ValueError("Exact original literal-loopback tile origin required")
        return value

    @model_validator(mode="after")
    def source_files(self) -> Self:
        acquisition, lifetime = self.operation, self.lifetime_operation
        if acquisition.mode != "execute" or lifetime.mode != "execute":
            raise ValueError(
                "Collection must freeze its acquisition and execute lifetime"
            )
        identity = (
            "run_id",
            "owner_id",
            "attempt_id",
            "allocation_id",
            "recovery_ref",
            "cancellation_ref",
        )
        if (
            any(getattr(acquisition, key) != getattr(lifetime, key) for key in identity)
            or lifetime.operation_id == acquisition.operation_id
            or lifetime.parent_operation_id in (None, lifetime.operation_id)
            or lifetime.deadline < acquisition.deadline
        ):
            raise ValueError("Explicit original resource lifetime and parent required")
        if {f.path for f in self.original_sources.files} != SOURCE_PATHS or any(
            f.executable or not 0 < f.size_bytes <= 1024**2
            for f in self.original_sources.files
        ):
            raise ValueError(
                "Exactly four complete bounded original frontend sources required"
            )
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class MapBrowserPublication(Contract):
    schema_version: Literal["map-browser-publication/1"] = "map-browser-publication/1"
    plan: MapPrivateArtifactPlan
    collection_sha256: Sha256
    handle: MapArtifactHandle
    terminal_readout: ReleaseFile
    observation_sha256: Sha256
    sequence: int = Field(ge=0)

    @model_validator(mode="after")
    def exact_handle(self) -> Self:
        if (
            self.plan.producer != "browser_process"
            or self.handle.plan_sha256 != self.plan.digest
        ):
            raise ValueError("Terminal publication changed original browser file plan")
        if (
            self.terminal_readout.path != "map-terminal-readout.json"
            or self.terminal_readout.executable
            or self.terminal_readout.size_bytes <= 0
        ):
            raise ValueError("Original complete terminal readout file required")
        return self
