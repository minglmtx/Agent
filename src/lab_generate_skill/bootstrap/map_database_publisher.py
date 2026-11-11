"""Existing complete native DB capture and artifact writer, owned by one worker."""

from pathlib import Path
from lab_generate_skill.domain.map_worker_inputs import MapWorkerInputs
from lab_generate_skill.domain.map_private_artifact import MapPrivateArtifactPlan
from lab_generate_skill.domain.map_database_artifact import MapDatabaseArtifact
from lab_generate_skill.domain.map_reference_selection import MapReferenceSelection
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.map_services import MapStartupControls
from lab_generate_skill.sites.map.native_database_capture import MapDatabaseCapture
from lab_generate_skill.sites.map.state_guard import MapStateGuard
from lab_generate_skill.adapters.map_runtime.database_export import (
    NativeMapDatabaseExportFiles,
)
from lab_generate_skill.adapters.map_artifacts.site_access import OriginalMapSiteAccess
from lab_generate_skill.adapters.map_artifacts.writer import MapArtifactWriter


class MapDatabasePublisher:
    def __init__(
        self,
        access: OriginalMapSiteAccess,
        guard: MapStateGuard,
        commands: NativeCommands,
        limits: MapStartupControls,
    ) -> None:
        self.access, self.guard, self.commands, self.limits = (
            access,
            guard,
            commands,
            limits,
        )
        self.writers: list[MapArtifactWriter] = []
        self.captures: list[MapDatabaseCapture] = []

    def publish(
        self,
        request: SiteCaptureRequest,
        selected: MapReferenceSelection,
        control: OperationControl,
    ) -> MapDatabaseArtifact:
        if not isinstance(self.access.inputs, MapWorkerInputs):
            raise ValueError("MapData database reference cannot dispatch navigation")
        plan = self.access.plan(request.inspection, control)
        if not isinstance(plan, MapPrivateArtifactPlan):
            raise ValueError("Original MapData artifact declaration required")
        writer = MapArtifactWriter(plan, Path(plan.workspace_root), self.access)
        self.writers.append(writer)
        writer.initialize(control)
        capture = MapDatabaseCapture(
            self.guard.spec,
            plan,
            self.guard,
            NativeMapDatabaseExportFiles(),
            self.commands,
            writer,
            self.limits,
        )
        self.captures.append(capture)
        result = capture.capture(
            selected.bounds, f"layer-final-{selected.request_index}", control
        )
        handle = writer.seal(control)
        return MapDatabaseArtifact(
            request=request,
            selected=selected,
            plan=plan,
            handle=handle,
            output=result.output,
            before_sha256=result.before_sha256,
            after_sha256=result.after_sha256,
        )
