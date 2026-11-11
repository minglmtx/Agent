"""Selected Map complete-file evidence declarations; no admission or task result."""

import hashlib
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self
from pydantic import Field, TypeAdapter, model_validator, field_validator
from .validation import Contract, Identifier, Sha256
from .lifecycle import AllocationToken
from .state_scope import StateScope
from .release import ReleaseArtifact, ReleaseFile
from .map_artifact_scope import check_artifact_scope
from .map_navigation_artifact import MapNavigationArtifactPlan


class MapPrivateArtifactPlan(Contract):
    schema_version: Literal["map-private-artifact-plan/1"] = (
        "map-private-artifact-plan/1"
    )
    scope: StateScope
    token: AllocationToken
    producer: Literal["browser_process", "native_database"]
    workspace_root: str
    private_root: str
    artifact_id: Identifier
    max_files: int = Field(ge=1, le=10000)
    max_file_bytes: int = Field(ge=1, le=2 * 1024**4)
    max_total_bytes: int = Field(ge=1, le=2 * 1024**4)

    @field_validator("workspace_root", "private_root")
    @classmethod
    def canonical(cls, value: str) -> str:
        p = PurePosixPath(value)
        if (
            not p.is_absolute()
            or str(p) != value
            or ".." in p.parts
            or any(c in value for c in ("\0", "\\"))
            or len(value) > 4096
        ):
            raise ValueError("Canonical absolute private artifact path required")
        return value

    @model_validator(mode="after")
    def binding(self) -> Self:
        task = self.scope.task
        if (
            task.site,
            task.family,
            task.contract_version,
            task.split,
            task.source_task_id,
            task.task_id,
        ) != (
            "map",
            "native_route_map_data",
            1,
            "train",
            "b9101b71aacd51b61f6e",
            "b9101b71aacd51b61f6e",
        ):
            raise ValueError(
                "Only selected original train MapData artifact scope supported"
            )
        check_artifact_scope(
            self.scope,
            self.token,
            self.producer,
            self.workspace_root,
            self.private_root,
            self.max_file_bytes,
            self.max_total_bytes,
        )
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


MapArtifactPlan = Annotated[
    MapPrivateArtifactPlan | MapNavigationArtifactPlan,
    Field(discriminator="schema_version"),
]
_plan_adapter: TypeAdapter[MapArtifactPlan] = TypeAdapter(MapArtifactPlan)


def parse_map_artifact_plan(value: object) -> MapArtifactPlan:
    return _plan_adapter.validate_python(value)


class MapArtifactManifest(Contract):
    schema_version: Literal["map-artifact-manifest/1"] = "map-artifact-manifest/1"
    plan: MapArtifactPlan
    artifact: ReleaseArtifact

    @model_validator(mode="after")
    def files(self) -> Self:
        p = self.plan
        a = self.artifact
        if (
            a.root != str(PurePosixPath(p.private_root) / "published" / "sealed")
            or a.artifact_id != p.artifact_id
            or len(a.files) > p.max_files
            or sum(f.size_bytes for f in a.files) > p.max_total_bytes
            or any(f.executable or f.size_bytes > p.max_file_bytes for f in a.files)
        ):
            raise ValueError("Published files differ from original plan/root/budgets")
        return self


class MapArtifactHandle(Contract):
    schema_version: Literal["map-artifact-handle/1"] = "map-artifact-handle/1"
    plan_sha256: Sha256
    manifest: ReleaseFile

    @model_validator(mode="after")
    def manifest_file(self) -> Self:
        if (
            self.manifest.path != "manifest.json"
            or self.manifest.executable
            or not 0 < self.manifest.size_bytes <= 8 * 1024**2
        ):
            raise ValueError("Bounded non-executable private manifest required")
        return self
