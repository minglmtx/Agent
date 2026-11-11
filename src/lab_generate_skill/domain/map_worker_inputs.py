"""Fixed selected Map runtime/source and private file roots; no permission."""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, field_validator, model_validator
from .validation import Contract, Sha256
from .state_scope import StateScope
from .map_runtime_inputs import MapRuntimeInputs
from .site_files import SiteFilesPlan


class MapWorkerInputs(Contract):
    schema_version: Literal["map-worker-inputs/1"] = "map-worker-inputs/1"
    runtime: MapRuntimeInputs
    scope: StateScope
    private_input_sha256: Sha256
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
        if self.runtime.readonly_inputs is not None:
            raise ValueError(
                "Readonly assets require the claimed navigation source consumer"
            )
        task = self.scope.task
        if (
            task.site,
            task.family,
            task.contract_version,
            task.split,
            task.task_id,
            task.source_task_id,
        ) != (
            "map",
            "native_route_map_data",
            1,
            "train",
            self.runtime.selected_source,
            self.runtime.selected_source,
        ):
            raise ValueError(
                "Only original selected train MapData worker scope supported"
            )
        check_worker_roots(
            self.runtime,
            self.evidence_root,
            self.resource_journal_root,
            self.artifact_root,
            self.max_file_bytes,
            self.max_total_bytes,
        )
        return self


def check_worker_roots(
    runtime: MapRuntimeInputs,
    evidence_root: str,
    resource_journal_root: str,
    artifact_root: str,
    max_file_bytes: int,
    max_total_bytes: int,
) -> None:
    if max_file_bytes > max_total_bytes:
        raise ValueError("Complete Map file exceeds total declared budget")
    workspace = PurePosixPath(runtime.files.workspace_root)
    roots = [
        PurePosixPath(p)
        for p in (
            evidence_root,
            resource_journal_root,
            artifact_root,
        )
    ]
    if any(p == workspace or not p.is_relative_to(workspace) for p in roots):
        raise ValueError("Original Map control/evidence roots must remain in workspace")
    if any(
        a.is_relative_to(b) or b.is_relative_to(a)
        for i, a in enumerate(roots)
        for b in roots[i + 1 :]
    ):
        raise ValueError(
            "Map full files, control CAS and resource journal must be separate"
        )
    inputs = (
        [PurePosixPath(t.source_root) for t in runtime.trees]
        + [PurePosixPath(x.source_path) for x in runtime.images]
        + [PurePosixPath(runtime.publication_path)]
        + [PurePosixPath(t.inventory_path) for t in runtime.trees]
    )
    if any(a.is_relative_to(b) or b.is_relative_to(a) for a in roots for b in inputs):
        raise ValueError("Map evidence/control roots overlap frozen runtime inputs")
