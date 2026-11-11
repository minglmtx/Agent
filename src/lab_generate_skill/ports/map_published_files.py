"""Complete original published Map members, guarded by original read authority."""

from typing import Protocol
from lab_generate_skill.domain.map_private_artifact import (
    MapArtifactHandle,
    MapArtifactManifest,
)
from .lifecycle import OperationControl


class MapPublishedFiles(Protocol):
    def manifest(
        self, handle: MapArtifactHandle, control: OperationControl
    ) -> MapArtifactManifest: ...
    def read(
        self, handle: MapArtifactHandle, name: str, control: OperationControl
    ) -> bytes: ...
