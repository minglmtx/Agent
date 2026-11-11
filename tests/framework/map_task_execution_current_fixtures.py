"""All production task producers/current file journals; explicit synthetic rights.

No real website/model/database or original source attempt. Every case owns a
fresh native task worker, browser, trace and configured synthetic 64K model.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.resource_records import (
    phase as browser_phase,
)
from lab_generate_skill.adapters.browsergym.retained_closure import (
    original_closed_browser,
)
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.adapters.map_artifacts.origin_authority import (
    OriginalMapOriginAuthority,
)
from site_resource_fixtures import Case
from lab_generate_skill.adapters.sites import step as site_step
from lab_generate_skill.adapters.browsergym import step as browser_step
from lab_generate_skill.bootstrap.task_execution import RecordedConstructionTask
from lab_generate_skill.bootstrap.map_task_execution import (
    map_navigation_task_execution,
    MapTaskExecution,
)
from lab_generate_skill.bootstrap.map_task_execution_bindings import (
    MapTaskExecutionDeclarations,
    MapTaskExecutionResources,
    MapTaskExecutionAuthorities,
    TaskInitialBinding,
)
from lab_generate_skill.bootstrap.task_actor import TaskActorResources
from lab_generate_skill.bootstrap.task_execution_composition import TaskExecutionRuntime
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.task_capture import TaskCapturePlan
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    InitializedTask,
    ClosedTaskResources,
)
from lab_generate_skill.domain.task_finalization import (
    TaskFinalizationPlan,
    UnstartedTaskBrowser,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from map_task_preparation_port_fixtures import preparation_case, MapPreparationPortCase
from map_task_execution_journal_fixtures import CurrentMapJournals, current_map_journals
from map_task_frozen_source_fixtures import frozen_map_unit_source, copy_frozen_source
from map_task_execution_initialization_fixtures import (
    CurrentMapHandles,
    current_initial_binding,
)
from map_task_execution_actor_fixtures import (
    UnitMapActorSource,
    current_map_actor_resources,
)
from map_closed_review_fixtures import closed_proof
from task_finalization_port_fixtures import (
    UnitFinalizationAuthority,
)
from actor_admission_fixtures import UnitActorAdmissionAuthority
from actor_long_fixtures import long_config
from source_actor_context_fixtures import source_context_case
from site_worker_fixtures import configuration
from test_slurm_commands import guard
from preparation_record_fixtures import put
import map_registered_worker_fixtures as registered


class UnitCurrentMapExecutionAuthority:
    def __init__(self, p: MapPreparationPortCase, h: CurrentMapHandles) -> None:
        self.p, self.h, self.denied = p, h, False

    def verify(
        self,
        plan: TaskExecutionPlan,
        progress: ConstructionProgress,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.denied:
            raise PermissionError("Synthetic original Map task source denied")
        assert plan == self.p.plan and reset == self.p.reset
        assert progress.project().pending_attempt == plan.intent
        assert snapshot.binding == plan.intent.binding.run
        if isinstance(self.p.site, RetainedSiteResource) and self.p.site.phase == "new":
            assert (
                self.p.original.worker is None
                and self.p.original.resource.channels == []
            )
            return
        assert (
            self.p.original.worker is not None
            and self.p.original.worker.tasks is not None
        )
        if self.p.preparation.state.phase in ("new", "binding", "acquired"):
            assert self.p.original.worker.tasks.phase == "new"

    def verify_closed(
        self,
        plan: TaskExecutionPlan,
        closed: ClosedTaskResources,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert plan == self.p.plan and closed.reset_plan == self.p.reset
        b = self.h.browser
        if b is None or b.phase == "new":
            assert (
                self.h.backend is None
                or self.h.backend.engines == []
                and self.h.backend.resource.channels == []
            )
            for value, ref in zip(closed.closures, closed.closure_refs, strict=True):
                assert (
                    self.p.original.resource.evidence.read(ref, control)
                    == value.model_dump_json().encode()
                )
                assert len(value.evidence) == 1
                raw = self.p.original.resource.evidence.read(value.evidence[0], control)
                original = UnstartedTaskBrowser.model_validate_json(raw)
                assert (
                    original.scope == self.p.reset.scope
                    and original.token == value.token
                )
            return
        read = browser_phase(operation, "current-map-closed-proof").model_copy(
            update={
                "attempt_id": b.spec.token.attempt_id,
                "parent_operation_id": b.operation.operation_id,
                "allocation_id": b.spec.token.allocation_id,
                "recovery_ref": b.spec.token.recovery_ref,
            }
        )
        record = original_closed_browser(
            b.spec,
            b.operation,
            read,
            b.journal,
            self.p.original.resource.evidence,
            control,
        )
        assert record.state == "closed" and b.phase == "closed"
        ending = json.loads(
            self.p.original.resource.evidence.read(
                record.events[-1].evidence[0], control
            )
        )
        actual = ClosureReceipt.model_validate_json(
            json.dumps(ending["details"]["closure"])
        )
        assert closed.closures == (actual,)
        assert (
            self.p.original.resource.evidence.read(closed.closure_refs[0], control)
            == actual.model_dump_json().encode()
        )


class UnitCurrentMapNonstart:
    def __init__(self, p: MapPreparationPortCase, h: CurrentMapHandles) -> None:
        self.p, self.h = p, h

    def close_unstarted(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        observed: UnstartedTaskBrowser,
        observed_ref: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        control.checkpoint()
        assert plan == self.p.plan and observed.scope == self.p.reset.scope
        assert self.h.browser is None or self.h.browser.phase == "new"
        assert (
            self.h.backend is None
            or self.h.backend.engines == []
            and self.h.backend.resource.channels == []
        )
        assert (
            self.p.original.resource.evidence.read(observed_ref, control)
            == observed.model_dump_json().encode()
        )
        return ClosureReceipt(
            token=observed.token,
            operation_id=operation.operation_id,
            status="closed",
            evidence=(observed_ref,),
        )


@dataclass
class CurrentMapExecutionCase:
    p: MapPreparationPortCase
    journals: CurrentMapJournals
    native: Any
    handles: CurrentMapHandles
    bundle: MapTaskExecution[RecordedConstructionTask]
    task_source: TaskSiteAuthority


@contextmanager
def current_map_execution_case(
    root: Path,
    patch: pytest.MonkeyPatch,
    source_id: str,
    *,
    negative: bool = False,
    deferred_site: bool = False,
    register_attempt: bool = True,
    current_task_results: bool = False,
) -> Iterator[CurrentMapExecutionCase]:
    native = source_context_case(root / "native64", patch, engine_config=long_config())

    def configured(*, job_id: str) -> SiteWorkerConfiguration:
        return configuration(job_id=native.scope.binding.resource.owner.job_id)

    patch.setattr(registered, "configuration", configured)
    native_source: TaskSiteAuthority | None = None

    def source(resource: Case) -> TaskSiteAuthority:
        nonlocal native_source

        def legacy(*args: object, **kwargs: object) -> None:
            pytest.fail(
                "Legacy resource/task fixture grant must not authorize current native requests"
            )

        patch.setattr(resource.authority, "verify_task", legacy)
        native_source = TaskSiteAuthority(
            resource.spec,
            resource.op,
            resource.authority,
            origin=OriginalMapOriginAuthority(
                contexts=None, evidence=None, source=None, read_operation=None
            ),
        )
        return native_source

    frozen_source = None
    original_source_store = None
    if deferred_site:
        frozen_source, original_source_store = frozen_map_unit_source(
            root / "independent-source", patch, source_id
        )

    site_root = root / "map-site"
    site_root.mkdir()
    try:
        with preparation_case(
            site_root,
            patch,
            source_id,
            site_authority_factory=source,
            deferred_site=deferred_site,
        ) as p:
            assert native_source is not None
            if frozen_source is not None:
                assert original_source_store is not None
                copy_frozen_source(
                    frozen_source, original_source_store, p.original.resource.evidence
                )
            journals = current_map_journals(
                p,
                native,
                p.original.workspace / "current-task-journals",
                frozen_source=frozen_source,
                register_attempt=register_attempt,
                current_task_results=current_task_results,
            )
            h = CurrentMapHandles()
            authority, actor = UnitCurrentMapExecutionAuthority(
                p, h
            ), UnitMapActorSource(p, native)
            final = UnitFinalizationAuthority(p, current_native=True)
            capture = TaskCapturePlan(
                scope=p.reset.scope,
                requirements=p.plan.evaluation.requirements,
                page_operation_id="current-map-page",
                close_operation_id="current-map-capture-close",
                guard_operation_id="current-map-guard",
                page_collector_id="map-navigation-page-health",
                page_collector_version="1",
                guard_collector_id="map-navigation-state",
                guard_collector_version="1",
                close_seconds=30,
            )
            ending = TaskFinalizationPlan(
                scope=p.reset.scope,
                browser_close_operation_id="current-map-final-close",
                restore_operation_id="current-map-restore",
                resume_operation_id="current-map-resume",
                qualification_operation_id="current-map-reset-facts",
                reset_operation_id="current-map-safe-reset",
            )
            d = MapTaskExecutionDeclarations(
                p.plan,
                p.declaration,
                p.reset,
                capture,
                put(p.original.resource.evidence, capture),
                ending,
                put(p.original.resource.evidence, ending),
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
                native_source,
            )
            runtime = TaskExecutionRuntime(
                journals.construction,
                journals.runs,
                journals.claims,
                journals.plans,
                authority,
                UnitActorAdmissionAuthority(),
                actor,
                p.original.resource.evidence,
                p.original.resource.controls,
                p.original.resource.clock,
            )
            bundle = map_navigation_task_execution(
                d,
                resources,
                MapTaskExecutionAuthorities(
                    final,
                    UnitCurrentMapNonstart(p, h),
                ),
                runtime,
            )
            p.preparation = bundle.preparation
            actor.bundle = bundle
            final.finalizer = bundle.finalization
            native.loader.session.output = native.loader.session.output.model_copy(
                update={"text": json.dumps({"action": "click('a')"})}
            )
            assert (
                p.requests == []
                and h.browser is None
                and native.loader.session.calls == 0
            )
            closed_proof(site_step, patch)
            try:
                yield CurrentMapExecutionCase(
                    p, journals, native, h, bundle, native_source
                )
            finally:
                if h.browser is not None and h.browser.phase == "open":
                    close = h.browser.operation.cleanup(
                        "current-original-fixture-close",
                        now=p.original.resource.clock.utcnow(),
                        seconds=30,
                    )
                    h.browser.close(close, h.browser.controls.bind(close))
    finally:
        native.client.close(guard(30))
