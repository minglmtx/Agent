"""One original browser writer; stop capability after native transport closure."""

from pathlib import Path
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.map_private_artifact import MapArtifactHandle
from lab_generate_skill.ports.lifecycle import OperationControl
from .browser_access import OriginalMapBrowserAccess
from .writer import MapArtifactWriter


class OriginalMapBrowserFiles:
    def __init__(self, access: OriginalMapBrowserAccess) -> None:
        if access.participant != "worker":
            raise ValueError("Only original browser worker can own file collection")
        self.access = access
        self.writer = MapArtifactWriter(
            access.plan, Path(access.plan.workspace_root), access
        )

    def initialize(self, control: OperationControl) -> None:
        self.writer.initialize(control)

    def retain(self, name: str, data: bytes, control: OperationControl) -> ReleaseFile:
        return self.writer.retain(name, data, control)

    def seal(self, control: OperationControl) -> MapArtifactHandle:
        return self.writer.seal(control)

    def stop_new_io(self) -> None:
        self.access.stop_new_io()
