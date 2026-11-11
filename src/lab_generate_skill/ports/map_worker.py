"""Worker storage lifecycle, retaining required original native state publication."""

from typing import Protocol
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.map_startup import MapStartupHttpResponse
from lab_generate_skill.domain.release import ReleaseFile
from .lifecycle import OperationControl
from .map_state_artifacts import MapStateArtifacts


class MapWorkerStorage(MapStateArtifacts, Protocol):
    def initialize(self, control: OperationControl) -> None: ...
    def bind_instance(
        self, started: SiteInstanceStarted, control: OperationControl
    ) -> None: ...
    def stop_new_io(self) -> None: ...
    def retain_startup_http(
        self, response: MapStartupHttpResponse, control: OperationControl
    ) -> ReleaseFile: ...
