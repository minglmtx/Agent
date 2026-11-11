"""Selected original Rails reference -> full private evidence -> native validation.

Runs only inside the original acquired site worker, with an admitted sink. This
consumer neither grants resource permission nor retries uncertain native calls.
"""

from dataclasses import dataclass
import hashlib
import json
import os
import threading
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OwnershipConflict,
)
from lab_generate_skill.domain.map_database_export import MapDatabaseExport
from lab_generate_skill.domain.map_private_artifact import MapPrivateArtifactPlan
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_database_export import MapDatabaseExportFiles
from lab_generate_skill.ports.map_private_artifact import MapArtifactSink
from lab_generate_skill.ports.map_services import MapStartupControls
from lab_generate_skill.ports.native_commands import NativeCommands
from .native_bounds import request_bounds
from .native_database import NativeDatabase, database_objects
from .native_database_program import reference_program
from .service_commands import container
from .state_guard import MapStateGuard
from .state_rules import object_json


@dataclass(frozen=True)
class CapturedMapDatabase:
    export: MapDatabaseExport
    output: ReleaseFile
    database: NativeDatabase
    before_sha256: str
    after_sha256: str


class MapDatabaseCapture:
    def __init__(
        self,
        spec: MapServiceSpec,
        artifacts: MapPrivateArtifactPlan,
        guard: MapStateGuard,
        files: MapDatabaseExportFiles,
        commands: NativeCommands,
        sink: MapArtifactSink,
        limits: MapStartupControls,
    ) -> None:
        self.spec = MapServiceSpec.model_validate(spec)
        self.artifacts = MapPrivateArtifactPlan.model_validate(artifacts)
        spec, artifacts = self.spec, self.artifacts
        if (
            artifacts.producer != "native_database"
            or artifacts.workspace_root != spec.inputs.files.workspace_root
            or artifacts.token.expected_resource_id != spec.inputs.files.instance_id
            or guard.spec != spec
            or guard.state != "ready"
        ):
            raise ValueError(
                "Original installed Map guard and matching site artifact plan required"
            )
        self.guard, self.files, self.commands, self.sink, self.limits = (
            guard,
            files,
            commands,
            sink,
            limits,
        )
        self.owner = os.getpid(), threading.get_ident()
        self.state = "ready"
        self.labels: set[str] = set()
        self.exports: list[MapDatabaseExport] = []
        self.retained: list[ReleaseFile] = []
        self.results: list[CapturedMapDatabase] = []
        self.error: BaseException | None = None

    def _retain(self, name: str, data: bytes, control: OperationControl) -> ReleaseFile:
        expected = ReleaseFile(
            path=name,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            executable=False,
        )
        actual = self.sink.retain(name, data, control)
        self.retained.append(actual)
        if actual != expected:
            raise EvidenceIntegrityError(
                "Native reference retention changed complete file identity"
            )
        return actual

    def capture(
        self, bounds: object, label: str, control: OperationControl
    ) -> CapturedMapDatabase:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original native reference worker/thread required")
        if self.state != "ready":
            raise InvalidTransition(
                "Failed or active native reference capture cannot repeat"
            )
        normalized = request_bounds(bounds)
        program = reference_program(normalized, label, self.artifacts.max_file_bytes)
        export = MapDatabaseExport(
            spec=self.spec,
            label=label,
            program=ReleaseFile(
                path="reference.rb",
                sha256=hashlib.sha256(program).hexdigest(),
                size_bytes=len(program),
                executable=False,
            ),
            max_output_bytes=self.artifacts.max_file_bytes,
        )
        if label in self.labels:
            raise InvalidTransition(
                "Original reference label cannot repeat; reuse its retained result"
            )
        control.checkpoint()
        self.labels.add(label)
        self.exports.append(export)
        self.state = "capturing"
        try:
            before = self.guard.require_unchanged(control)
            self._retain(
                label + "-intent.json",
                json.dumps(
                    dict(
                        export=export.model_dump(mode="json"),
                        artifact_plan_sha256=self.artifacts.digest,
                        before_sha256=before.sha256,
                    ),
                    sort_keys=True,
                ).encode(),
                control,
            )
            self._retain(label + "-reference.rb", program, control)
            self.files.prepare(export, program, control)
            self.guard.services.require_running()
            self.commands.run(
                container(self.spec, "web", app=True)
                + ("bundle", "exec", "rails", "runner", export.container_program),
                self.limits.bind(control, "database_reference"),
            )
            raw = self.files.read(export, control)
            output = self._retain(export.output_name, raw, control)
            database = database_objects(object_json(raw), normalized)
            after = self.guard.require_unchanged(control)
            self._retain(
                label + "-complete.json",
                json.dumps(
                    dict(
                        output=output.model_dump(mode="json"),
                        artifact_plan_sha256=self.artifacts.digest,
                        before_sha256=before.sha256,
                        after_sha256=after.sha256,
                    ),
                    sort_keys=True,
                ).encode(),
                control,
            )
            result = CapturedMapDatabase(
                export, output, database, before.sha256, after.sha256
            )
            self.results.append(result)
            control.checkpoint()
            self.state = "ready"
            return result
        except BaseException as error:
            self.state, self.error = "failed", error
            raise
