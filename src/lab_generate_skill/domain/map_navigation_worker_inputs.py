"""Concrete selected navigation declaration; runtime provenance stays unchanged."""

from typing import Literal, Self
from pydantic import Field, field_validator, model_validator
from .validation import Contract, Sha256
from .state_scope import StateScope
from .map_runtime_inputs import MapRuntimeInputs
from .map_navigation_scope import check_navigation_scope
from .map_worker_inputs import check_worker_roots
from .site_files import SiteFilesPlan
from .map_origin import MapOriginPolicy


class MapNavigationWorkerInputs(Contract):
    schema_version: Literal["map-navigation-worker-inputs/2"] = (
        "map-navigation-worker-inputs/2"
    )
    origin: MapOriginPolicy
    runtime: MapRuntimeInputs
    scope: StateScope
    private_input_sha256: Sha256
    native_contract_sha256: Sha256
    evidence_root: str
    resource_journal_root: str
    artifact_root: str
    max_files: int = Field(ge=1, le=10000)
    max_file_bytes: int = Field(ge=1, le=2 * 1024**4)
    max_total_bytes: int = Field(ge=1, le=2 * 1024**4)

    @field_validator("evidence_root", "resource_journal_root", "artifact_root")
    @classmethod
    def canonical(cls, value: str) -> str:
        return SiteFilesPlan.canonical(value)

    @model_validator(mode="after")
    def selected_source_and_roots(self) -> Self:
        if (
            self.runtime.readonly_inputs is not None
            and self.origin.mode != "frozen_context"
        ):
            raise ValueError(
                "Readonly assets require the original qualified source context"
            )
        check_navigation_scope(self.scope.task, self.native_contract_sha256)
        check_worker_roots(
            self.runtime,
            self.evidence_root,
            self.resource_journal_root,
            self.artifact_root,
            self.max_file_bytes,
            self.max_total_bytes,
        )
        return self
