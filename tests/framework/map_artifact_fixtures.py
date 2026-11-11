"""Explicit synthetic authority; file identity tests never admit a production source."""

from pathlib import Path
from typing import Literal
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.map_private_artifact import (
    MapPrivateArtifactPlan,
    MapArtifactPlan,
)
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.map_artifacts.writer import MapArtifactWriter
from test_core_contracts import reference
from lab_generate_skill.domain.lifecycle import AllocationToken, ResourceOwner


class Authority:
    denied = False

    def __init__(self, plan: MapPrivateArtifactPlan) -> None:
        self.plan = plan
        self.calls: list[str] = []

    def verify(
        self,
        plan: MapArtifactPlan,
        phase: Literal["initialize", "write", "seal", "read"],
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls.append(phase)
        if plan != self.plan or self.denied:
            raise PermissionError("fixture original authority denied")


def case(
    root: Path,
    *,
    file_budget: int = 256 * 1024 * 1024,
    total_budget: int = 512 * 1024 * 1024,
    max_files: int = 100,
) -> tuple[MapArtifactWriter, Authority]:
    original = AllocationToken(
        allocation_id="browser-allocation",
        owner=ResourceOwner(
            run_id="run", owner_id="owner", job_id="engineering", worker_id="original"
        ),
        resource_kind="browser",
        scope="attempt",
        attempt_id="attempt",
        expected_resource_id="browser",
        provider_id="fixed-browser-worker",
        provider_version="3",
        recovery_ref=reference("private", "recovery-plan/1"),
    )
    task = TaskIdentity(
        source_task_id="b9101b71aacd51b61f6e",
        task_id="b9101b71aacd51b61f6e",
        site="map",
        family="native_route_map_data",
        contract_version=1,
        split="train",
    )
    scope = StateScope(
        owner=original.owner, task=task, attempt_id="attempt", context_id="context"
    )
    plan = MapPrivateArtifactPlan(
        scope=scope,
        token=original,
        producer="browser_process",
        workspace_root=str(root),
        private_root=str(root / "private-files"),
        artifact_id="map-native",
        max_files=max_files,
        max_file_bytes=file_budget,
        max_total_bytes=total_budget,
    )
    authority = Authority(plan)
    return MapArtifactWriter(plan, root, authority), authority
