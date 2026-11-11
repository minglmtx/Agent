"""Real original RPC/CAS/registered browser; explicit synthetic rights/services.

Only initialization is under test. The held browser is closed by this fixture;
this is not task completion, a real source claim, or a restoration receipt.
"""

from collections.abc import Iterator, Callable
from map_navigation_browser_fixtures import Page
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import pytest
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.adapters.browsergym.resource_records import put as resource_put
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.bootstrap.map_task_initialization import (
    map_navigation_task_initialization,
)
from lab_generate_skill.bootstrap.map_task_preparation import map_task_preparation
from lab_generate_skill.bootstrap.map_overlay_records import map_prepared_browser_checks
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.baseline import BaselineInputs, BaselineReceipt
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureIntent,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    RecoveryPlan,
)
from lab_generate_skill.domain.optional_policies import InactivePolicy
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.task_initialization import (
    TaskInitializationPlan,
    TaskActorInitialization,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_context_projection_fixtures import actor_projection_case
from browser_worker_fixtures import configuration
from context_budget_fixtures import profile
from context_storage_fixtures import UnitContextAuthority
from map_browser_native import declarations
from map_preparation_native import MapPreparation
from lab_generate_skill.domain.skill import CompactSkill
from map_navigation_browser_resource_fixtures import (
    NavigationBrowserDouble,
    navigation_browser_resource,
)
from map_navigation_group_cases import SOURCES
from map_task_preparation_port_fixtures import MapPreparationPortCase, preparation_case
from preparation_record_fixtures import put
from retrieval_fixtures import reference
from task_initialization_source_fixtures import historical_source


class UnitNavigationContextAuthority(UnitContextAuthority):
    def verify_baseline(
        self, inputs: BaselineInputs, receipt: BaselineReceipt, op: OperationContext
    ) -> None:
        self.calls.append("baseline")
        if self.denied:
            raise PermissionError("Synthetic historical baseline denied")

    def verify_reset(
        self, inputs: ResetInputs, receipt: ResetReceipt, op: OperationContext
    ) -> None:
        self.calls.append("reset")
        if self.denied:
            raise PermissionError("Synthetic historical reset denied")


class UnitInitializationAuthority:
    def __init__(self) -> None:
        self.denied = False
        self.calls: list[OperationContext] = []

    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskInitializationPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls.append(operation)
        assert plan.intent.binding.task == declaration.scope.task
        if self.denied:
            raise PermissionError("Synthetic initialization admission denied")


class UnitInitialAuthority:
    def verify(
        self,
        inputs: InitialObservationInputs,
        checks: StateChecks,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert inputs.observation.record.sequence == 0


class UnitCaptureAuthority:
    def __init__(
        self, p: MapPreparationPortCase, browser: RetainedBrowserResource
    ) -> None:
        self.p, self.browser = p, browser
        self.denied = False

    def verify_capture(
        self,
        configuration: BrowserWorkerConfiguration,
        request: BrowserCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        intent = BrowserCaptureIntent.model_validate_json(
            self.p.original.resource.evidence.read(intent_ref, control=control)
        )
        assert intent.request == request
        assert (
            intent.configuration_sha256
            == hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
        )
        observed = self.browser.session.observation_ref
        assert observed is not None
        assert request.observation_sha256 == observed.sha256
        if self.denied:
            raise PermissionError("Synthetic passive capture denied")


@dataclass
class InitializationPortCase:
    preparation: MapPreparationPortCase
    initialization: RecordedTaskInitialization
    backend: NavigationBrowserDouble
    browser: RetainedBrowserResource
    authority: UnitInitializationAuthority
    context_authority: UnitNavigationContextAuthority
    capture_authority: UnitCaptureAuthority

    def start(self) -> InitializedTask:
        p = self.preparation
        op = p.operation("starting")
        return self.initialization.start(
            p.plan, op, p.original.resource.controls.bind(op)
        )


@contextmanager
def initialization_case(
    root: Path,
    patch: pytest.MonkeyPatch,
    source_id: str = SOURCES[0],
    *,
    freeze_run: Callable[[MapPreparationPortCase], TaskExecutionPlan] | None = None,
    step_effect: Callable[[Page, str], None] | None = None,
    public_text: str = "[1] link About\n[2] link Help",
) -> Iterator[InitializationPortCase]:
    with preparation_case(root, patch, source_id) as p:
        c, n = p.original, p.source.native
        assert isinstance(n, MapPreparation)
        _, original_context, context_ref = historical_source(p)
        # This is before any candidate task snapshot/prepare. No claim changes or
        # restarted native task; the old unused adapter has never dispatched.
        assert p.preparation.state.phase == "new" and p.requests == []
        skill = CompactSkill.model_validate_json(
            c.resource.evidence.read(p.plan.skill_ref)
        )
        p.plan = p.plan.model_copy(
            update={
                "intent": p.plan.intent.model_copy(
                    update={
                        "public_context_ref": original_context.public_context_ref,
                        "skill_digest": skill.content_digest,
                    }
                )
            }
        )
        if freeze_run is not None:
            p.plan = TaskExecutionPlan.model_validate(freeze_run(p))
        p.preparation = map_task_preparation(
            p.plan,
            p.declaration,
            c.resource.spec,
            p.site,
            c.resource.journal,
            c.resource.evidence,
            c.resource.controls,
            n.bindings,
            p.authority,
        )
        p.authority.preparation = p.preparation
        p.acquire()
        p.prepare()
        state = p.preparation.state
        assert state.result is not None and state.result_ref is not None
        n.request, n.result, n.environment = (
            state.prepare_request,
            state.prepare_result,
            state.environment,
        )
        base = configuration(c.configuration.installation)
        session = base.spec.model_copy(
            update={"scope": c.scope, "task": n.public, "max_events": 4096}
        )
        browser_root = c.workspace / "initialization-browser"
        browser_root.mkdir()
        cfg, browser_operation = declarations(
            n,
            p.site.site,
            state.result.publication,
            session,
            base,
            browser_root,
            p.reset.attempt_allocations[0],
            started_ref=state.original_acquired().site_started_ref,
        )
        backend = navigation_browser_resource(
            browser_root,
            patch,
            configuration=cfg,
            store=c.resource.evidence,
            declared_token=p.reset.attempt_allocations[0],
            site=c.resource.spec,
            public_text=public_text,
            step_effect=step_effect,
        )
        b = backend.resource
        b.op = browser_operation.model_copy(
            update={
                "deadline": min(browser_operation.deadline, p.plan.operation.deadline)
            }
        )
        binding = PreparedBrowserBinding(
            state.result.publication,
            c.resource.spec,
            p.site.site,
            c.resource.op,
            evidence=c.resource.evidence,
            preparations=n.records,
            journal=c.resource.journal,
            task_checks=map_prepared_browser_checks(
                c.resource.evidence, c.configuration, p.site.site.instance
            ),
        )
        browser = RetainedBrowserResource(
            b.spec,
            b.op,
            journal=b.journal,
            evidence=b.evidence,
            controls=b.controls,
            clock=b.clock,
            authority=PreparedBrowserAuthority(b.spec, binding, b.authority),
        )
        parameters = reference(
            {"unit_model_parameters": True, "schema_version": "model-parameters/1"},
            "model-parameters/1",
            store=c.resource.evidence,
        )
        actor_config = ActorContextConfiguration(
            policy=actor_projection_case(site="map").policy,
            profiles=(
                profile(
                    provider="fixed-actor-worker",
                    configuration_ref=parameters,
                    context_window=65536,
                    output_reserve=4096,
                    input_limit=61440,
                    soft_target=24576,
                ),
            ),
        )
        actor_recovery = RecoveryPlan(
            recovery_id="unit-actor-close",
            owner=c.scope.owner,
            baseline_ref=n.spec_ref,
            restore_component_id="unit-actor-close",
            restore_component_version="1",
            state_coverage=("unit-actor",),
        )
        actor_token = AllocationToken(
            allocation_id="unit-actor",
            owner=c.scope.owner,
            scope="batch",
            resource_kind="actor",
            expected_resource_id="unit-actor-resource",
            provider_id="fixed-actor-worker",
            provider_version="1",
            recovery_ref=put(c.resource.evidence, actor_recovery),
        )
        actor = TaskActorInitialization(
            candidate_id="candidate-zero",
            revision_round=0,
            context_configuration_ref=put(c.resource.evidence, actor_config),
            memory=InactivePolicy(status="disabled", reason="explicit unit fixture"),
            model_allocation=actor_token,
            parameters_refs=(parameters,),
            generation_seconds=30,
            interaction_seconds=30,
            cleanup_seconds=30,
        )
        declaration = TaskInitializationPlan(
            scope=c.scope,
            prepared_result_ref=state.result_ref,
            source_context_receipt_ref=context_ref,
            browser_spec_ref=resource_put(
                b.evidence,
                b.spec.model_dump_json().encode(),
                b.spec.schema_version,
                b.controls.bind(b.op),
            ),
            browser_acquisition=b.op,
            capture_operation=b.op.model_copy(
                update={"operation_id": "initial-passive-capture"}
            ),
            initial_operation=p.operation("initial-checks"),
            baseline_operation=p.operation("baseline"),
            comparison_operation=p.operation("compare"),
            equivalence_operation=p.operation("equivalence"),
            actor=actor,
        )
        authority = UnitInitializationAuthority()
        contexts = UnitNavigationContextAuthority()
        capture = UnitCaptureAuthority(p, browser)
        initializer = map_navigation_task_initialization(
            p.plan,
            declaration,
            put(c.resource.evidence, declaration),
            browser,
            n.records,
            authority,
            contexts,
            contexts,
            capture,
            UnitInitialAuthority(),
            c.resource.evidence,
            c.resource.controls,
        )
        try:
            yield InitializationPortCase(
                p, initializer, backend, browser, authority, contexts, capture
            )
        finally:
            if browser.phase == "open":
                cleanup = b.op.cleanup(
                    "unit-initialization-close",
                    now=datetime.now(timezone.utc),
                    seconds=30,
                )
                browser.close(cleanup, b.controls.bind(cleanup))
