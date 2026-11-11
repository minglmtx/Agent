"""Owned Map complete-file root and state publisher, preserving partial effects."""

from pathlib import Path
import hashlib
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.map_state_artifact import MapStateArtifact
from lab_generate_skill.domain.map_startup import (
    MapStartupHttpFailureRecord,
    MapStartupHttpResponse,
)
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.artifact_copy import sync_directory
from .files import private_directory, write_once
from .site_access import OriginalMapSiteAccess
from .state_publisher import MapStatePublisher


class OriginalMapStateStorage:
    def __init__(self, access: OriginalMapSiteAccess) -> None:
        if access.participant != "worker":
            raise ValueError("Only original worker initializes Map file storage")
        self.access = access
        self.root = Path(access.inputs.artifact_root)
        self.publisher = MapStatePublisher(
            Path(access.configuration.files.workspace_root), access, access
        )
        self.state = "new"
        self.error: BaseException | None = None

    def initialize(self, control: OperationControl) -> None:
        if self.state != "new":
            raise InvalidTransition(
                "Map private file root initialization cannot repeat"
            )
        self.access.observe(control)
        self.state = "initializing"
        try:
            private_directory(self.root.parent)
            self.root.mkdir(mode=0o700)
            private_directory(self.root)
            sync_directory(self.root)
            sync_directory(self.root.parent)
            control.checkpoint()
            self.state = "ready"
        except BaseException as error:
            self.state, self.error = "failed", error
            raise

    def bind_instance(
        self, started: SiteInstanceStarted, control: OperationControl
    ) -> None:
        if self.state != "ready":
            raise InvalidTransition("Original Map file root required before binding")
        self.access.bind_instance(started, control)

    def publish(
        self,
        request: SiteTaskRequest,
        data: bytes,
        state_sha256: str,
        control: OperationControl,
    ) -> MapStateArtifact:
        if self.state != "ready":
            raise InvalidTransition("Original Map storage is not ready")
        return self.publisher.publish(request, data, state_sha256, control)

    def stop_new_io(self) -> None:
        self.state = "stopped"
        self.access.stop_new_io()

    def retain_startup_http(
        self, response: MapStartupHttpResponse, control: OperationControl
    ) -> ReleaseFile:
        response = MapStartupHttpResponse.model_validate(response)
        if self.state != "ready" or self.access.started is not None:
            raise InvalidTransition(
                "Only original unstarted Map storage retains startup failure"
            )
        self.access.observe(control)
        record = MapStartupHttpFailureRecord(
            scope=self.access.inputs.scope,
            instance_id=self.access.configuration.files.instance_id,
            configuration_sha256=hashlib.sha256(
                self.access.configuration.model_dump_json().encode()
            ).hexdigest(),
            writer=current_process_identity(),
            response=response,
        )
        raw = record.model_dump_json().encode()
        if (
            len(raw) > self.access.inputs.max_file_bytes
            or len(raw) > self.access.inputs.max_total_bytes
        ):
            raise ValueError(
                "Startup diagnostic exceeds original private storage bounds"
            )
        self.state = "startup-failure"
        try:
            private_directory(self.root)
            entry = write_once(
                self.root, "startup-http-failure.json", raw, control, readonly=True
            )
            self.access.observe(control)
            return entry
        except BaseException as error:
            self.error = error
            raise
