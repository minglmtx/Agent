"""Original worker/read authority is required; a file plan grants no permission."""

from typing import Literal, Protocol
from lab_generate_skill.domain.map_private_artifact import MapArtifactPlan
from .lifecycle import OperationControl
from lab_generate_skill.domain.release import ReleaseFile


class MapArtifactAuthority(Protocol):
    def verify(
        self,
        plan: MapArtifactPlan,
        phase: Literal["initialize", "write", "seal", "read"],
        control: OperationControl,
    ) -> None:
        """Bind original acquisition/configuration, worker and attempt, no default allow."""
        ...


class MapArtifactSink(Protocol):
    def retain(
        self, name: str, data: bytes, control: OperationControl
    ) -> "ReleaseFile":
        """Durably retain original bytes once; failure leaves original candidate files."""
        ...
