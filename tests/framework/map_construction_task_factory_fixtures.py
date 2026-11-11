"""Pure current original Map command/deps fixture, no alternate execution entry."""

from pathlib import Path
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.application.task_execution_evidence import (
    TaskExecutionEvidenceDeps,
)
from map_construction_task_evidence_fixtures import UnitCurrentTaskConstructionAuthority
import pytest
from lab_generate_skill.application.construct_targets import (
    ConstructionDeps,
    ConstructionReadiness,
    construct_targets,
)
from lab_generate_skill.application.construction_task_preparation import (
    ActorPreparationDeps,
    prepare_actor_step,
)
from lab_generate_skill.bootstrap.construction_task_execution import (
    construction_task_dependencies,
    RecordedConstructionTasks,
)
from lab_generate_skill.bootstrap.task_execution import RecordedConstructionTask
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.domain.construction import AttemptIntent
from lab_generate_skill.domain.construction_task_preparation import ActorPreparation
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from map_task_execution_current_fixtures import current_map_execution_case
from map_task_execution_review_fixtures import current_map_review_facts
from map_navigation_evaluation_fixtures import closed_review
from map_navigation_group_cases import SOURCES
from site_instance_fixtures import node_path as node_path


from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from lab_generate_skill.domain.construction_preparation import PublishedConstructionStep
from map_task_execution_current_fixtures import CurrentMapExecutionCase


@dataclass
class MapControlCase:
    actual: CurrentMapExecutionCase
    deps: ConstructionDeps
    saved: PublishedConstructionStep
    calls: list[AttemptIntent]


@contextmanager
def original_map_control_case(
    root: Path, patch: pytest.MonkeyPatch, source_id: str, *, negative: bool = False
) -> Iterator[MapControlCase]:
    with current_map_execution_case(
        root,
        patch,
        source_id,
        negative=negative,
        deferred_site=True,
        register_attempt=False,
        current_task_results=True,
    ) as case:
        p, bundle, j = case.p, case.bundle, case.journals
        assert isinstance(j.data.authority, UnitCurrentTaskConstructionAuthority)
        assert isinstance(p.site, RetainedSiteResource)
        j.data.authority.reads = TaskExecutionEvidenceDeps(
            p.original.resource.evidence,
            j.runs,
            EvidenceStateRecords(
                p.original.resource.evidence, p.original.resource.controls, j.context
            ),
            bundle.task.deps.authority,
        )
        j.data.authority.site = p.site
        j.data.authority.contexts = EvidenceContextRecords(
            p.original.resource.evidence, p.original.resource.controls, j.context
        )
        before = j.construction.read(p.plan.read_operation)
        assert (
            before.project().pending_attempt is None
            and before.project().next_action.kind == "execute"
        )
        d = ConstructionDeps(
            j.construction,
            p.original.resource.controls,
            readiness=ConstructionReadiness(
                j.runs, j.claims, j.plans, j.data.authority
            ),
            evidence=p.original.resource.evidence,
        )
        seen = []

        def factory(
            intent: AttemptIntent, op: OperationContext, control: OperationControl
        ) -> RecordedConstructionTask:
            control.checkpoint()
            assert intent == p.plan.intent and op == p.plan.operation
            assert (
                j.construction.read(p.plan.read_operation).project().pending_attempt
                == intent
            )
            assert isinstance(p.site, RetainedSiteResource) and p.site.phase == "new"
            assert (
                p.original.resource.channels == []
                and case.native.loader.session.calls == 0
            )
            seen.append(intent)
            return bundle.task

        deps = construction_task_dependencies(
            d, p.plan.read_operation, j.construction, factory
        )
        prepare_op = p.plan.read_operation.model_copy(
            update={"operation_id": "original-map-actor-command"}
        )
        request = ActorPreparation(
            run=p.plan.intent.binding.run,
            expected_revision=before.revision,
            task=p.plan,
            operation=prepare_op,
            completion_operation=prepare_op.cleanup(
                "original-map-task-completed",
                now=p.original.resource.clock.utcnow(),
                seconds=30,
            ),
        )
        saved = prepare_actor_step(
            request, ActorPreparationDeps(deps, p.original.resource.evidence)
        )
        assert seen == [] and case.native.loader.session.calls == 0
        yield MapControlCase(case, deps, saved, seen)
