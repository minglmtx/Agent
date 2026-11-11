"""Small binding to the complete native DB export; no comparison verdict."""

import hashlib
from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract, Sha256
from .site_capture import SiteCaptureRequest
from .map_reference_selection import MapReferenceSelection
from .map_private_artifact import MapPrivateArtifactPlan, MapArtifactHandle
from .map_state_artifact import check_state_plan
from .release import ReleaseFile


class MapDatabaseArtifact(Contract):
    schema_version: Literal["map-database-artifact/1"] = "map-database-artifact/1"
    request: SiteCaptureRequest
    selected: MapReferenceSelection
    plan: MapPrivateArtifactPlan
    handle: MapArtifactHandle
    output: ReleaseFile
    before_sha256: Sha256
    after_sha256: Sha256

    @model_validator(mode="after")
    def original(self) -> Self:
        check_state_plan(self.plan, self.request.inspection)
        raw = self.selected.model_dump_json().encode()
        ref = self.request.selection_ref
        if (
            ref is None
            or (ref.sha256, ref.size_bytes)
            != (hashlib.sha256(raw).hexdigest(), len(raw))
            or (self.request.collector_id, self.request.collector_version)
            != ("map-native-reference", "1")
            or self.selected.inspection_sha256 != self.request.inspection.digest
            or self.handle.plan_sha256 != self.plan.digest
            or self.output.path
            != f"osm-expanded-layer-final-{self.selected.request_index}.json"
            or self.output.executable
            or not 0 < self.output.size_bytes <= self.plan.max_file_bytes
            or self.before_sha256 != self.after_sha256
        ):
            raise ValueError(
                "Original selected request and complete unchanged native DB export required"
            )
        return self
