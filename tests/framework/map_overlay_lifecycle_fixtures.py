"""Real Map private trees/guard/reset/artifact/CAS; native services/SQL are synthetic."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Generic, TypeVar
from lab_generate_skill.adapters.map_artifacts.state_publisher import MapStatePublisher
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.map_private_artifact import (
    MapPrivateArtifactPlan,
    MapArtifactPlan,
)
from lab_generate_skill.domain.map_state_artifact import MapStateArtifact
from lab_generate_skill.domain.map_navigation_artifact import MapNavigationArtifactPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.overlay_spec import NativeOverlaySpec
from lab_generate_skill.sites.map.tasks.state_lifecycle import MapTaskLifecycle
from lab_generate_skill.sites.map.tasks.state_codec import MapTaskStateCodec
from lab_generate_skill.sites.map.tasks.state_resume import MapTaskResume
from map_artifact_fixtures import case as artifact_case
from map_frontend_reset_fixtures import reset_case
from map_service_generations_fixtures import GenerationCase
from test_core_contracts import reference
from test_slurm_commands import guard

PlanT = TypeVar("PlanT", MapPrivateArtifactPlan, MapNavigationArtifactPlan)


class ExplicitPlansAndAuthority(Generic[PlanT]):
    """Only test-declared requests/plans; not a production permission source."""

    def __init__(self, base: PlanT) -> None:
        self.base: PlanT = base
        self.plans: dict[str, PlanT] = {}
        self.denied = False
        self.calls: list[str] = []

    def plan(self, request: SiteTaskRequest, control: OperationControl) -> PlanT:
        control.checkpoint()
        value = type(self.base).model_validate(
            {
                **self.base.model_dump(),
                "private_root": str(
                    Path(self.base.workspace_root)
                    / "task-state"
                    / request.operation.operation_id
                ),
                "artifact_id": request.operation.operation_id,
            }
        )
        self.plans[value.digest] = value
        return value

    def verify(
        self,
        plan: MapArtifactPlan,
        phase: Literal["initialize", "write", "seal", "read"],
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls.append(phase)
        if self.denied or self.plans.get(plan.digest) != plan:
            raise PermissionError("original synthetic test permission denied")


class OverlayCase:
    def __init__(self, generations: GenerationCase) -> None:
        self.generations = generations
        self.reset, self.sql, self.root = reset_case(generations)
        spec = generations.case.spec
        self.workspace = Path(spec.inputs.files.workspace_root)
        self.workspace.chmod(0o700)
        (self.workspace / "task-state").mkdir(mode=0o700)
        old = artifact_case(self.workspace)[0].plan
        token = {
            **old.token.model_dump(),
            "resource_kind": "site",
            "scope": "batch",
            "attempt_id": None,
            "expected_resource_id": spec.inputs.files.instance_id,
            "provider_id": "fixed-site-worker",
            "provider_version": "5",
        }
        self.plan = MapPrivateArtifactPlan.model_validate(
            {**old.model_dump(), "producer": "native_database", "token": token}
        )
        self.authority = ExplicitPlansAndAuthority(self.plan)
        self.publisher = MapStatePublisher(
            self.workspace, self.authority, self.authority
        )
        self.lifecycle = MapTaskLifecycle(
            self.reset.guard,
            self.reset,
            self.publisher,
            MapTaskStateCodec(self.plan.scope.task),
        )
        self.resume = MapTaskResume(self.lifecycle)
        (self.workspace / "control-cas").mkdir(mode=0o700)
        self.store = FileEvidenceStore(self.workspace / "control-cas")
        self.spec = NativeOverlaySpec(
            task=self.plan.scope.task,
            native_contract_ref=reference("private", "map-native-contract/1"),
        )
        self.binding = self.put(b'{"fixture":"original binding"}', "task-binding/1")
        self.task_recovery = self.put(
            b'{"fixture":"original task recovery"}', "recovery-plan/1"
        )
        self.snapshot_ref: EvidenceRef | None = None

    def put(self, data: bytes, schema: str) -> EvidenceRef:
        return self.store.put(
            data,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="fixture-map-control",
            ),
        )

    def request(
        self, action: str, label: str | None = None, **changes: Any
    ) -> SiteTaskRequest:
        op = OperationContext(
            operation_id=label or action,
            run_id=self.plan.scope.owner.run_id,
            owner_id=self.plan.scope.owner.owner_id,
            attempt_id=self.plan.scope.attempt_id,
            allocation_id=self.plan.token.allocation_id,
            recovery_ref=self.task_recovery,
            deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
            mode="cleanup" if action == "restore" else "execute",
            parent_operation_id=(
                (
                    self.lifecycle.preparation or self.lifecycle.snapshot.request
                ).operation.operation_id
                if action == "restore" and self.lifecycle.snapshot
                else None
            ),
        )
        raw: dict[str, Any] = dict(
            task=self.plan.scope.task,
            binding_ref=self.binding,
            operation=op,
            action=action,
            snapshot_ref=None if action == "snapshot" else self.snapshot_ref,
            private_input=self.spec.model_dump_json(),
        )
        raw.update(changes)
        return SiteTaskRequest.model_validate(raw)

    def snapshot(self) -> SiteTaskResult:
        result = self.lifecycle.execute_task(self.request("snapshot"), control=guard())
        self.snapshot_ref = self.put(
            result.private_result.encode(), "map-overlay-snapshot/1"
        )
        return result

    def prepare(self) -> SiteTaskResult:
        self.snapshot()
        return self.lifecycle.execute_task(self.request("prepare"), control=guard())

    def resume_request(self, restored: SiteTaskResult) -> SiteResumeRequest:
        old = self.lifecycle.restore_request
        assert old is not None
        op = OperationContext.model_validate(
            {
                **old.operation.model_dump(),
                "operation_id": "resume",
                "parent_operation_id": old.operation.operation_id,
                "recovery_ref": self.plan.token.recovery_ref,
            }
        )
        return SiteResumeRequest(
            restore_request=old,
            restore_result_ref=self.put(
                restored.model_dump_json().encode(), "site-task-result/1"
            ),
            operation=op,
        )

    def read(self, native: MapStateArtifact) -> bytes:
        return MapArtifactReader(native.plan, self.workspace, self.authority).read(
            native.handle, native.file.path, guard()
        )
