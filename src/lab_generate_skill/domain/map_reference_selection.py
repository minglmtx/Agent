"""A selected original response for one inspection, not permission to query DB.

The parent recomputes the complete terminal evidence. The original site worker
checks the inspection and private selection before the existing DB capture.
"""

from typing import Annotated, Literal, Self
from pydantic import Field, StringConstraints, model_validator
from .validation import Contract, Sha256
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .map_private_artifact import MapArtifactHandle
from .release import ReleaseFile

CoordinateText = Annotated[str, StringConstraints(min_length=1, max_length=256)]


class MapReferenceSelection(Contract):
    schema_version: Literal["map-reference-selection/1"] = "map-reference-selection/1"
    inspection_sha256: Sha256
    terminal_selection_ref: EvidenceRef
    terminal_handle: MapArtifactHandle
    request_index: int = Field(ge=0, le=255)
    bounds: tuple[CoordinateText, CoordinateText, CoordinateText, CoordinateText]
    response_kind: Literal["native_200", "adapted_union"]
    payload: ReleaseFile
    records_sha256: Sha256

    @model_validator(mode="after")
    def original_response(self) -> Self:
        private_state_ref(self.terminal_selection_ref, "map-terminal-selection/1")
        if (
            self.terminal_selection_ref.media_type != "application/json"
            or self.payload.path != f"request-{self.request_index}-response.bin"
            or self.payload.executable
            or not 0 < self.payload.size_bytes <= 2 * 1024**4
        ):
            raise ValueError(
                "Exact private terminal selection and complete response required"
            )
        return self

    @property
    def original_request_key(self) -> tuple[str, int]:
        # A new inspection/selection ID cannot make the original browser request
        # new again. Full pin equality is checked when reusing its first result.
        return self.terminal_handle.plan_sha256, self.request_index
