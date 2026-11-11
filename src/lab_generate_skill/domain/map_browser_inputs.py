"""Frozen selected browser collection roots; no permission or readiness claim."""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import field_validator, model_validator
from .validation import Contract
from .map_private_artifact import MapPrivateArtifactPlan
from .site_files import SiteFilesPlan
from .map_browser_collection import MapBrowserCollectionSpec


class MapBrowserInputs(Contract):
    schema_version: Literal["map-browser-inputs/2"] = "map-browser-inputs/2"
    plan: MapPrivateArtifactPlan
    evidence_root: str
    resource_journal_root: str
    collection: MapBrowserCollectionSpec

    @field_validator("evidence_root", "resource_journal_root")
    @classmethod
    def canonical(cls, value: str) -> str:
        return SiteFilesPlan.canonical(value)

    @model_validator(mode="after")
    def original_roots(self) -> Self:
        if self.plan.producer != "browser_process":
            raise ValueError("Original Map browser file plan required")
        token, op = self.plan.token, self.collection.operation
        if (
            op.run_id,
            op.owner_id,
            op.attempt_id,
            op.allocation_id,
            op.recovery_ref,
        ) != (
            token.owner.run_id,
            token.owner.owner_id,
            token.attempt_id,
            token.allocation_id,
            token.recovery_ref,
        ):
            raise ValueError("Map collection changed original resource operation")
        workspace = PurePosixPath(self.plan.workspace_root)
        roots = tuple(
            PurePosixPath(p)
            for p in (
                self.plan.private_root,
                self.evidence_root,
                self.resource_journal_root,
                self.collection.original_sources.root,
            )
        )
        if any(p == workspace or not p.is_relative_to(workspace) for p in roots):
            raise ValueError(
                "Map browser files and original records must stay in workspace"
            )
        if any(
            a.is_relative_to(b) or b.is_relative_to(a)
            for i, a in enumerate(roots)
            for b in roots[i + 1 :]
        ):
            raise ValueError(
                "Map browser files, original CAS and journal must be separate"
            )
        return self
