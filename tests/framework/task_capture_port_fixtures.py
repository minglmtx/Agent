"""Actual initialized Actor2/context/trace -> current terminal capture/evaluator.

Model/counts/page/native services/physical/source grants are explicit doubles.
No second initialization, Actor runner or original business request is created.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import pytest
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.sites.task_capture import RecordedTaskCapture
from lab_generate_skill.bootstrap.map_task_capture import (
    map_navigation_task_capture,
    CapturedNavigationEvaluator,
)
from lab_generate_skill.bootstrap.task_capture_inputs import (
    initialized_task_capture_inputs,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_capture import TaskCapturePlan, TaskCaptureInputs
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    TaskCaptureResult,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.evaluators.map.navigation import REQUIREMENTS
from map_actor_trace_fixtures import execute_browser_actor
from map_navigation_group_cases import SOURCES, MEMBERS
from map_navigation_browser_fixtures import Page
from map_site_capture_native import MapCaptureAuthority
from map_site_engineering_authority import MapEngineeringAuthority
from map_task_preparation_port_fixtures import MapPreparationPortCase
from preparation_record_fixtures import put
from retrieval_fixtures import reference
from task_capture_actor_fixtures import freeze_run, controlled_context
from task_initialization_port_fixtures import (
    InitializationPortCase,
    initialization_case,
)


class UnitTaskCaptureAuthority:
    def __init__(self) -> None:
        self.denied = False
        self.calls: list[OperationContext] = []

    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskCapturePlan,
        inputs: TaskCaptureInputs,
        snapshot: TraceSnapshot,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert snapshot.plan.binding == plan.intent.binding
        assert inputs.initialized.actor.scope == declaration.scope
        self.calls.append(operation)
        if self.denied:
            raise PermissionError("Synthetic original task capture permission denied")


class UnitSiteCaptureAuthority(MapCaptureAuthority):
    def __init__(self, p: MapPreparationPortCase) -> None:
        # Explicit synthetic passive-capture grant, independent of the original
        # site/native supplier. Reuse all existing exact private/recovery/intent
        # checks without replacing the current resource source authority.
        authority = MapEngineeringAuthority(
            p.original.resource, Path(p.original.configuration.files.node_root).parent
        )
        authority.before_native = True
        authority.task_input = p.source.native.private_input_json()
        super().__init__(p.source, task_authority=authority)
        self.p, self.calls, self.denied = p, 0, False

    def verify_capture(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.denied:
            raise PermissionError("Synthetic complete final guard permission denied")
        authority = self.task_authority
        assert isinstance(authority, MapEngineeringAuthority)
        assert request.operation.operation_id not in authority.task_intents
        authority.task_intents[request.operation.operation_id] = (
            self.p.source.native.put(request.inspection)
        )
        super().verify_capture(configuration, request, intent_ref, control)
        self.calls += 1


@dataclass
class CapturePortCase:
    initial: InitializationPortCase
    capture: RecordedTaskCapture
    evaluator: CapturedNavigationEvaluator
    authority: UnitTaskCaptureAuthority
    site_authority: UnitSiteCaptureAuthority
    journals: list[FileTraceJournal]
    snapshot: TraceSnapshot | None = None

    def actor(self) -> TraceSnapshot:
        p, i = self.initial.preparation, self.initial
        result = i.start()
        assert result.actor.schema_version == "actor-run-request/2"
        _, _, _, snapshot = execute_browser_actor(
            p.original,
            i.backend.resource,
            i.browser.session,
            request=result.actor,
            binding=p.plan.intent.binding,
            context_factory=lambda r, j: controlled_context(
                r, j, p.original.resource.evidence
            ),
            on_journal=self.journals.append,
        )
        self.snapshot = snapshot
        return snapshot

    def collect(self) -> TaskCaptureResult:
        assert self.snapshot is not None
        p = self.initial.preparation
        op = p.plan.operation.model_copy(
            update={"operation_id": p.plan.operation.operation_id + ".capture"}
        )
        return self.capture.capture(
            p.plan, self.snapshot, op, p.original.resource.controls.bind(op)
        )


@contextmanager
def capture_case(
    root: Path,
    patch: pytest.MonkeyPatch,
    source_id: str = SOURCES[0],
    *,
    negative: bool = False,
) -> Iterator[CapturePortCase]:
    row = next(row for row in MEMBERS if row[0] == source_id)
    target, heading = row[1:]
    if negative:
        target, heading = "/about", "Wrong named document"

    def effect(page: Page, payload: str) -> None:
        assert payload == "click('a')"
        page.url = "/".join(page.url.split("/", 3)[:3]) + target
        page.headings = [heading]

    def bound_run(p: MapPreparationPortCase) -> TaskExecutionPlan:
        plan = freeze_run(p)
        return plan.model_copy(
            update={
                "evaluation": plan.evaluation.model_copy(
                    update={"requirements": REQUIREMENTS}
                )
            }
        )

    with initialization_case(
        root,
        patch,
        source_id,
        freeze_run=bound_run,
        step_effect=effect,
        public_text="RootWebArea 'Map navigation'\n  [a] link 'Requested local document'",
    ) as i:
        p, init = i.preparation, i.initialization
        store = p.original.resource.evidence
        # Freeze well-formed v2 settings before browser acquisition. These are
        # software parameters; no real model/tokenizer qualification is implied.
        params = LocalActorParameters(
            max_input_tokens=61440,
            max_new_tokens=4096,
            seed=0,
            temperature=0.0,
            top_p=1.0,
        )
        params_ref = reference(params, "model-parameters/1", store=store)
        actor = init.declaration.actor
        cfg = ActorContextConfiguration.model_validate_json(
            store.read(actor.context_configuration_ref)
        )
        cfg = cfg.model_copy(
            update={
                "profiles": tuple(
                    profile.model_copy(update={"configuration_ref": params_ref})
                    for profile in cfg.profiles
                )
            }
        )
        actor = actor.model_copy(
            update={
                "parameters_refs": (params_ref,),
                "context_configuration_ref": put(store, cfg),
            }
        )
        init.declaration = init.declaration.model_copy(update={"actor": actor})
        init.declaration_ref = put(store, init.declaration)
        d = TaskCapturePlan(
            scope=p.declaration.scope,
            requirements=REQUIREMENTS,
            page_operation_id="task-terminal-page",
            close_operation_id="task-terminal-browser-close",
            guard_operation_id="task-terminal-complete-guard",
            page_collector_id="map-navigation-page-health",
            page_collector_version="1",
            guard_collector_id="map-navigation-state",
            guard_collector_version="1",
            close_seconds=p.plan.cleanup_seconds,
        )
        journals: list[FileTraceJournal] = []
        authority, site_authority = (
            UnitTaskCaptureAuthority(),
            UnitSiteCaptureAuthority(p),
        )
        capture, evaluator = map_navigation_task_capture(
            p.plan,
            d,
            put(store, d),
            lambda control: initialized_task_capture_inputs(
                p.preparation, init, control
            ),
            lambda: i.browser,
            lambda: journals[0],
            p.site,
            p.original.resource.spec,
            p.source.native.records,
            authority,
            i.capture_authority,
            site_authority,
            store,
            p.original.resource.controls,
            p.original.resource.clock,
        )
        assert journals == [] and i.browser.phase == "new"
        capture.preflight(
            p.plan,
            evaluator.requirements(p.plan.evaluation),
            p.original.resource.controls.bind(p.plan.operation),
        )
        assert journals == [] and i.browser.phase == "new"
        yield CapturePortCase(
            i, capture, evaluator, authority, site_authority, journals
        )
