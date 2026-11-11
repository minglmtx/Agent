"""Original acquired site publishes full state through admitted private files."""

from typing import Protocol
from lab_generate_skill.domain.map_state_artifact import MapStateArtifact
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.map_private_artifact import MapArtifactPlan
from .lifecycle import OperationControl


class MapStateArtifacts(Protocol):
    def publish(
        self,
        request: SiteTaskRequest,
        data: bytes,
        state_sha256: str,
        control: OperationControl,
    ) -> MapStateArtifact:
        """Admit original task/resource, retain all bytes and seal once.

        Each request gets an exclusive original artifact plan. Unknown writes or
        seal results do not authorize retry. Returned handles are independently
        readable under the original authority, outside mutable node state.
        """
        ...


class MapStateArtifactPlans(Protocol):
    def plan(
        self, request: SiteTaskRequest, control: OperationControl
    ) -> MapArtifactPlan:
        """Resolve predeclared original task/instance plan; this grants no permission."""
        ...


class MapStateFileReader(Protocol):
    def read(
        self,
        descriptor: MapStateArtifact,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> bytes:
        """Read all original immutable bytes under original participant authority."""
        ...
