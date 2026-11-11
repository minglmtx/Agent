"""Single-source default Map ABC on original ports; native services/rights unit.

No construction journal, Generator or Teacher record. Each case has an
independent source and a fresh candidate worker, browser and trace.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from lab_generate_skill.adapters.map_artifacts.origin_authority import (
    OriginalMapOriginAuthority,
)
from lab_generate_skill.adapters.sites import step as site_step
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.bootstrap.execution_task import RecordedExecutionTask
from lab_generate_skill.bootstrap.map_task_execution import (
    map_navigation_task_execution,
    MapTaskExecution,
    MapExecutionTaskRuntime,
)
from lab_generate_skill.bootstrap.map_task_execution_bindings import (
    MapTaskExecutionDeclarations,
    MapTaskExecutionResources,
    MapExecutionTaskAuthorities,
    TaskInitialBinding,
)
from lab_generate_skill.bootstrap.task_actor import TaskActorResources
from lab_generate_skill.domain.actor_admission import CandidateFacts, PreparedActorInput
from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.task_capture import TaskCapturePlan
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    InitializedTask,
    ClosedTaskResources,
)
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_long_fixtures import long_config
from map_closed_review_fixtures import closed_proof
from map_execution_task_source_fixtures import SingleMapJournals, single_map_journals
from map_navigation_next_group_fixtures import AdditionalStartPage, ROWS
from map_navigation_browser_fixtures import Page
from map_task_execution_actor_fixtures import (
    UnitMapActorSource,
    current_map_actor_resources,
)
from map_task_execution_current_fixtures import (
    UnitCurrentMapExecutionAuthority,
    UnitCurrentMapNonstart,
)
from map_task_execution_initialization_fixtures import (
    CurrentMapHandles,
    current_initial_binding,
)
from map_task_frozen_source_fixtures import frozen_map_unit_source, copy_frozen_source
from map_task_preparation_port_fixtures import preparation_case, MapPreparationPortCase
from preparation_record_fixtures import put
from site_resource_fixtures import Case
from site_worker_fixtures import configuration
from source_actor_context_fixtures import source_context_case
from task_finalization_port_fixtures import UnitFinalizationAuthority
from test_slurm_commands import guard
import map_registered_worker_fixtures as registered


class UnitSingleMapAuthority:
    def __init__(self, p: MapPreparationPortCase, h: CurrentMapHandles) -> None:
        self.p, self.h, self.denied = p, h, False
        self.closed = UnitCurrentMapExecutionAuthority(p, h)
        self.initial_calls = 0

    def verify(
        self,
        plan: TaskExecutionPlan,
        source: ExecutionSourceFacts,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.denied:
            raise PermissionError("Synthetic single Map resources revoked")
        assert plan == self.p.plan and reset == self.p.reset
        assert source.source.intent == plan.intent
        assert source.source.run == snapshot.binding
        assert source.source.task == self.p.source.native.binding

    def verify_initial(
        self,
        plan: TaskExecutionPlan,
        source: ExecutionSourceFacts,
        facts: CandidateFacts,
        snapshot: RunSnapshot,
        control: OperationControl,
    ) -> None:
        self.verify(plan, source, snapshot, self.p.reset, control)
        self.initial_calls += 1
        assert facts.source == source.context
        assert facts.task_binding == source.source.task
        assert self.h.browser is not None and self.h.browser.phase == "open"

    def verify_closed(
        self,
        plan: TaskExecutionPlan,
        closed: ClosedTaskResources,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self.closed.verify_closed(plan, closed, operation, control)


@dataclass
class SingleMapExecutionCase:
    p: MapPreparationPortCase
    journals: SingleMapJournals
    native: SimpleNamespace
    handles: CurrentMapHandles
    bundle: MapTaskExecution[RecordedExecutionTask]
    authority: UnitSingleMapAuthority
    actor: UnitMapActorSource
    final: UnitFinalizationAuthority


@contextmanager
def single_map_execution_case(
    root: Path, patch: pytest.MonkeyPatch, source_id: str, *, negative: bool = False
) -> Iterator[SingleMapExecutionCase]:
    native = source_context_case(root / "native64", patch, engine_config=long_config())

    def configured(*, job_id: str) -> SiteWorkerConfiguration:
        return configuration(job_id=native.scope.binding.resource.owner.job_id)

    patch.setattr(registered, "configuration", configured)
    frozen, oldstore = frozen_map_unit_source(
        root / "independent-source", patch, source_id
    )
    sources: list[TaskSiteAuthority] = []

    def source(resource: Case) -> TaskSiteAuthority:
        def legacy(*args: object, **kwargs: object) -> None:
            pytest.fail("Legacy task dictionary may not authorize current single Map")

        patch.setattr(resource.authority, "verify_task", legacy)
        value = TaskSiteAuthority(
            resource.spec,
            resource.op,
            resource.authority,
            origin=OriginalMapOriginAuthority(
                contexts=None, evidence=None, source=None, read_operation=None
            ),
        )
        sources.append(value)
        return value

    site_root = root / "map-site"
    site_root.mkdir()
    try:
        with preparation_case(
            site_root,
            patch,
            source_id,
            site_authority_factory=source,
            deferred_site=True,
        ) as p:
            copy_frozen_source(frozen, oldstore, p.original.resource.evidence)
            journals = single_map_journals(
                p, native, p.original.workspace / "single-journals", frozen
            )
            h = CurrentMapHandles()
            authority = UnitSingleMapAuthority(p, h)
            actor = UnitMapActorSource(p, native)
            final = UnitFinalizationAuthority(p, current_native=True)
            capture = TaskCapturePlan(
                scope=p.reset.scope,
                requirements=p.plan.evaluation.requirements,
                page_operation_id="single-map-page",
                close_operation_id="single-map-capture-close",
                guard_operation_id="single-map-guard",
                page_collector_id="map-navigation-page-health",
                page_collector_version="1",
                guard_collector_id="map-navigation-state",
                guard_collector_version="1",
                close_seconds=30,
            )
            ending = TaskFinalizationPlan(
                scope=p.reset.scope,
                browser_close_operation_id="single-map-final-close",
                restore_operation_id="single-map-restore",
                resume_operation_id="single-map-resume",
                qualification_operation_id="single-map-reset-facts",
                reset_operation_id="single-map-safe-reset",
            )
            store, controls = p.original.resource.evidence, p.original.resource.controls
            declarations = MapTaskExecutionDeclarations(
                p.plan,
                p.declaration,
                p.reset,
                capture,
                put(store, capture),
                ending,
                put(store, ending),
            )

            branch = next(
                r["initial_branch"] for r in ROWS if r["source_task_id"] == source_id
            )
            page_type = (
                AdditionalStartPage
                if branch in ("search", "directions", "traces")
                else Page
            )

            def initial(
                prep: RecordedSiteTaskPreparation,
                operation: OperationContext,
                control: OperationControl,
            ) -> TaskInitialBinding:
                return current_initial_binding(
                    p,
                    journals,
                    native,
                    h,
                    patch,
                    prep,
                    operation,
                    control,
                    negative=negative,
                    page_type=page_type,
                )

            def actor_resources(
                initialized: InitializedTask, prepared: PreparedActorInput
            ) -> TaskActorResources:
                return current_map_actor_resources(p, native, h, initialized, prepared)

            resources = MapTaskExecutionResources(
                p.original.resource.spec,
                p.site,
                p.original.resource.journal,
                p.original.resource.journal,
                p.source.native.bindings,
                lambda: h.browser,
                lambda: h.trace,
                initial,
                actor_resources,
                sources[0],
            )
            runtime = MapExecutionTaskRuntime(
                journals.source_reader,
                journals.runs,
                journals.claims,
                authority,
                store,
                controls,
                p.original.resource.clock,
                journals.plans,
            )
            bundle = map_navigation_task_execution(
                declarations,
                resources,
                MapExecutionTaskAuthorities(final, UnitCurrentMapNonstart(p, h), actor),
                runtime,
            )
            p.preparation = bundle.preparation
            actor.bundle, final.finalizer = bundle, bundle.finalization
            native.loader.session.output = native.loader.session.output.model_copy(
                update={"text": json.dumps({"action": "click('a')"})}
            )
            assert (
                not p.requests
                and h.browser is None
                and native.loader.session.calls == 0
            )
            closed_proof(site_step, patch)
            try:
                yield SingleMapExecutionCase(
                    p, journals, native, h, bundle, authority, actor, final
                )
            finally:
                if h.browser is not None and h.browser.phase == "open":
                    op = h.browser.operation.cleanup(
                        "single-fixture-close",
                        now=p.original.resource.clock.utcnow(),
                        seconds=30,
                    )
                    h.browser.close(op, h.browser.controls.bind(op))
    finally:
        native.client.close(guard(30))
