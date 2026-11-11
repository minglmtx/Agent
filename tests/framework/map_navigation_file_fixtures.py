"""Exact navigation inputs and explicit synthetic file permission; no native site."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from typing import Literal
from lab_generate_skill.adapters.map_artifacts.site_plan import original_site_plan
from lab_generate_skill.domain.map_private_artifact import MapArtifactPlan
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.map_origin import MapOriginPolicy
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.ports.lifecycle import OperationControl
from map_navigation_fixtures import navigation_case, SOURCES
from map_runtime_fixtures import runtime_case
from site_worker_fixtures import configuration
from test_core_contracts import reference


@dataclass(frozen=True)
class NavigationFiles:
    configuration: SiteWorkerConfiguration
    request: SiteTaskRequest
    workspace: Path

    @property
    def inputs(self) -> MapNavigationWorkerInputs:
        value = self.configuration.map_inputs
        assert isinstance(value, MapNavigationWorkerInputs)
        return value


def navigation_files(root: Path, source: str = SOURCES[0]) -> NavigationFiles:
    selected = navigation_case(source).load().private_spec
    runtime = runtime_case(root)
    base = configuration()
    token = base.token.model_copy(
        update={"expected_resource_id": runtime.files.instance_id}
    )
    workspace = Path(runtime.files.workspace_root)
    workspace.chmod(0o700)
    (workspace / "navigation-files").mkdir(mode=0o700)
    private = selected.model_dump_json()
    inputs = MapNavigationWorkerInputs(
        origin=MapOriginPolicy.dynamic(),
        runtime=runtime,
        scope=StateScope(
            owner=token.owner,
            task=selected.task,
            attempt_id="navigation-attempt",
            context_id="navigation-context",
        ),
        private_input_sha256=hashlib.sha256(private.encode()).hexdigest(),
        native_contract_sha256=selected.native_contract_ref.sha256,
        evidence_root=str(workspace / "evidence"),
        resource_journal_root=str(workspace / "journal"),
        artifact_root=str(workspace / "navigation-files"),
        max_files=4,
        max_file_bytes=128 * 1024**2,
        max_total_bytes=128 * 1024**2,
    )
    cfg = SiteWorkerConfiguration(
        site_id="map",
        token=token,
        files=runtime.files,
        apptainer="/usr/bin/apptainer",
        installation=base.installation,
        private_evidence=None,
        map_inputs=inputs,
    )
    req = SiteTaskRequest.model_validate(
        dict(
            task=selected.task,
            binding_ref=reference("private", "task-binding/1"),
            operation=dict(
                operation_id="snapshot",
                run_id=token.owner.run_id,
                owner_id=token.owner.owner_id,
                attempt_id=inputs.scope.attempt_id,
                allocation_id=token.allocation_id,
                recovery_ref=reference("private", "recovery-plan/1"),
                deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
                mode="execute",
            ),
            action="snapshot",
            snapshot_ref=None,
            private_input=private,
        )
    )
    return NavigationFiles(cfg, req, workspace)


class DeclaredFilePermission:
    """Software-only stand-in for independently checked acquisition/ownership."""

    def __init__(self, files: NavigationFiles) -> None:
        self.files = files
        self.declared: dict[str, MapArtifactPlan] = {}
        self.phases: list[str] = []
        self.read_only = False

    def plan(
        self, request: SiteTaskRequest, control: OperationControl
    ) -> MapArtifactPlan:
        control.checkpoint()
        plan = original_site_plan(self.files.configuration, request)
        self.declared[plan.digest] = plan
        return plan

    def verify(
        self,
        plan: MapArtifactPlan,
        phase: Literal["initialize", "write", "seal", "read"],
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.phases.append(phase)
        if self.declared.get(plan.digest) != plan or self.read_only and phase != "read":
            raise PermissionError("Explicit synthetic original-file permission denied")
