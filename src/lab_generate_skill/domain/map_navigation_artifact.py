"""Concrete navigation native-state file plan on the existing full-file port."""

import hashlib
from typing import Literal, Self
from pydantic import Field, field_validator, model_validator
from .validation import Contract, Identifier, Sha256
from .lifecycle import AllocationToken
from .state_scope import StateScope
from .site_files import SiteFilesPlan
from .map_artifact_scope import check_artifact_scope
from .map_navigation_scope import check_navigation_scope


class MapNavigationArtifactPlan(Contract):
    schema_version: Literal["map-navigation-artifact-plan/1"] = (
        "map-navigation-artifact-plan/1"
    )
    scope: StateScope
    token: AllocationToken
    producer: Literal["native_database"]
    workspace_root: str
    private_root: str
    artifact_id: Identifier
    max_files: int = Field(ge=1, le=10000)
    max_file_bytes: int = Field(ge=1, le=2 * 1024**4)
    max_total_bytes: int = Field(ge=1, le=2 * 1024**4)
    native_contract_sha256: Sha256

    @field_validator("workspace_root", "private_root")
    @classmethod
    def canonical(cls, value: str) -> str:
        return SiteFilesPlan.canonical(value)

    @model_validator(mode="after")
    def binding(self) -> Self:
        check_navigation_scope(self.scope.task, self.native_contract_sha256)
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
