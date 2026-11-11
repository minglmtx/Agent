"""Full small instance, real files/evidence, explicitly synthetic native SQL/Rails."""

import json
from pathlib import Path
from typing import Any
from lab_generate_skill.adapters.map_artifacts.writer import MapArtifactWriter
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from lab_generate_skill.adapters.map_runtime.database_export import (
    NativeMapDatabaseExportFiles,
)
from lab_generate_skill.domain.map_private_artifact import MapPrivateArtifactPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.native_database import DATABASE_VERSION
from lab_generate_skill.sites.map.native_database_capture import MapDatabaseCapture
from lab_generate_skill.sites.map.service_commands import container
from map_artifact_fixtures import case as artifact_case, Authority
from map_instance_fixtures import InstanceCase
from map_state_fixtures import state_case
from test_slurm_commands import guard

BOUNDS = ("0", "0", "0.1", "0.1")


def payload() -> dict[str, Any]:
    return dict(
        version=DATABASE_VERSION,
        bounds=list(BOUNDS),
        initial_node_ids=["1"],
        nodes=[dict(id="1", version="1", lat="0", lon="0", tags={})],
        ways=[],
        relations=[],
    )


class CaptureCase:
    def __init__(self, case: InstanceCase) -> None:
        self.case = case
        self.tracker, self.sql, self.persistent = state_case(case)
        self.tracker.install(guard())
        workspace = Path(case.spec.inputs.files.workspace_root)
        workspace.chmod(0o700)
        writer, _ = artifact_case(workspace)
        old = writer.plan
        token = {
            **old.token.model_dump(),
            "resource_kind": "site",
            "scope": "batch",
            "attempt_id": None,
            "expected_resource_id": case.spec.inputs.files.instance_id,
            "provider_id": "fixed-site-worker",
            "provider_version": "candidate-test",
        }
        self.plan = MapPrivateArtifactPlan.model_validate(
            {**old.model_dump(), "producer": "native_database", "token": token}
        )
        self.authority = Authority(self.plan)
        self.writer = MapArtifactWriter(self.plan, workspace, self.authority)
        self.writer.initialize(guard())
        self.files = NativeMapDatabaseExportFiles()
        self.calls: list[tuple[str, ...]] = []
        self.body = json.dumps(payload()).encode()
        self.fail: BaseException | None = None
        self.dirty = False
        self.capture = self.build()

    def build(self, **changes: Any) -> MapDatabaseCapture:
        args: dict[str, Any] = dict(
            spec=self.case.spec,
            artifacts=self.plan,
            guard=self.tracker,
            files=self.files,
            commands=self,
            sink=self.writer,
            limits=BoundedMapStartupControls(),
        )
        args.update(changes)
        return MapDatabaseCapture(**args)

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        control.checkpoint()
        self.calls.append(argv)
        export = self.capture.exports[-1]
        assert argv == container(self.case.spec, "web", app=True) + (
            "bundle",
            "exec",
            "rails",
            "runner",
            export.container_program,
        )
        path = Path(export.host_directory) / export.output_name
        with path.open("xb") as stream:
            stream.write(self.body)
        path.chmod(0o400)
        if self.dirty:
            (self.persistent / "public/some-asset.js").write_bytes(
                b"unexpected persistent change"
            )
        if self.fail is not None:
            raise self.fail
        return b"native runner diagnostic stdout is not reference data\n"
