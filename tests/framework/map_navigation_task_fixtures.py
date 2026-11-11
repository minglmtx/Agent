"""Navigation codecs on existing small physical guard/reset fixtures, no website."""

from typing import Any
from lab_generate_skill.adapters.map_artifacts.state_publisher import MapStatePublisher
from lab_generate_skill.domain.map_navigation_artifact import MapNavigationArtifactPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.sites.map.tasks.state_lifecycle import MapTaskLifecycle
from lab_generate_skill.sites.map.tasks.state_resume import MapTaskResume
from lab_generate_skill.sites.map.tasks.state_codec import MapTaskStateCodec
from map_overlay_lifecycle_fixtures import OverlayCase, ExplicitPlansAndAuthority
from map_service_generations_fixtures import GenerationCase
from map_navigation_fixtures import navigation_case
from test_slurm_commands import guard


class NavigationTaskCase:
    def __init__(self, generations: GenerationCase, source: str) -> None:
        physical = OverlayCase(generations)
        self.physical = physical
        self.spec = navigation_case(source).load().private_spec
        self.workspace, self.reset, self.sql = (
            physical.workspace,
            physical.reset,
            physical.sql,
        )
        self.plan = MapNavigationArtifactPlan.model_validate(
            {
                **physical.plan.model_dump(),
                "schema_version": "map-navigation-artifact-plan/1",
                "scope": {**physical.plan.scope.model_dump(), "task": self.spec.task},
                "native_contract_sha256": self.spec.native_contract_ref.sha256,
            }
        )
        self.authority = ExplicitPlansAndAuthority(self.plan)
        self.publisher = MapStatePublisher(
            self.workspace, self.authority, self.authority
        )
        self.lifecycle = MapTaskLifecycle(
            self.reset.guard,
            self.reset,
            self.publisher,
            MapTaskStateCodec(self.spec.task),
        )
        self.resume = MapTaskResume(self.lifecycle)
        self.snapshot_ref: EvidenceRef | None = None

    def request(
        self, action: str, label: str | None = None, **changes: Any
    ) -> SiteTaskRequest:
        original = self.physical.request("snapshot", label or action).model_dump()
        op = original["operation"]
        op["mode"] = "cleanup" if action == "restore" else "execute"
        if action == "restore" and self.lifecycle.snapshot is not None:
            op["parent_operation_id"] = (
                self.lifecycle.preparation or self.lifecycle.snapshot.request
            ).operation.operation_id
        value = {
            **original,
            "task": self.spec.task,
            "action": action,
            "private_input": self.spec.model_dump_json(),
            "snapshot_ref": None if action == "snapshot" else self.snapshot_ref,
        }
        value.update(changes)
        return SiteTaskRequest.model_validate(value)

    def snapshot(self) -> SiteTaskResult:
        result = self.lifecycle.execute_task(self.request("snapshot"), control=guard())
        self.snapshot_ref = self.physical.put(
            result.private_result.encode(), "map-navigation-snapshot/1"
        )
        return result

    def prepare(self) -> SiteTaskResult:
        self.snapshot()
        return self.lifecycle.execute_task(self.request("prepare"), control=guard())

    def resume_request(self, restored: SiteTaskResult) -> SiteResumeRequest:
        old = self.lifecycle.restore_request
        assert old is not None
        return SiteResumeRequest.model_validate(
            dict(
                restore_request=old,
                restore_result_ref=self.physical.put(
                    restored.model_dump_json().encode(), "site-task-result/1"
                ),
                operation={
                    **old.operation.model_dump(),
                    "operation_id": "resume",
                    "parent_operation_id": old.operation.operation_id,
                    "recovery_ref": self.plan.token.recovery_ref,
                },
            )
        )
