"""Complete original sources and original file lifecycle; no native browser dispatch."""

from collections.abc import Mapping
from typing import Protocol
from lab_generate_skill.domain.map_private_artifact import MapArtifactHandle
from .map_private_artifact import MapArtifactSink
from .lifecycle import OperationControl


class MapBrowserSources(Protocol):
    def read(self, control: OperationControl) -> Mapping[str, bytes]: ...


class MapBrowserFiles(MapArtifactSink, Protocol):
    def initialize(self, control: OperationControl) -> None: ...
    def seal(self, control: OperationControl) -> MapArtifactHandle: ...
    def stop_new_io(self) -> None: ...


class MapBrowserLifetime(OperationControl, Protocol):
    def intersect(self, caller: OperationControl) -> OperationControl:
        """Keep the original collection lifetime; a later caller cannot renew it."""
        ...
