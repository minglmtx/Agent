"""Late actual initialization declarations over explicit synthetic page/kernel rights."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.resource_records import put as resource_put
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.bootstrap.actor_context_runtime import freeze_actor_context
from lab_generate_skill.bootstrap.map_overlay_records import map_prepared_browser_checks
from lab_generate_skill.bootstrap.map_task_execution_bindings import TaskInitialBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.optional_policies import InactivePolicy
from lab_generate_skill.domain.task_initialization import (
    TaskInitializationPlan,
    TaskActorInitialization,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from map_browser_native import declarations
from map_preparation_native import MapPreparation
from map_navigation_browser_fixtures import Page
from map_navigation_browser_resource_fixtures import (
    navigation_browser_resource,
    NavigationBrowserDouble,
)
from map_task_preparation_port_fixtures import MapPreparationPortCase
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.contexts import ContextAuthority
from lab_generate_skill.domain.evidence import EvidenceRef
import json
import re
from preparation_record_fixtures import put
from task_initialization_port_fixtures import UnitCaptureAuthority, UnitInitialAuthority
from browser_worker_fixtures import configuration
import pytest
from map_closed_review_fixtures import closed_proof
from lab_generate_skill.adapters.browsergym import step as browser_step


@dataclass
class CurrentMapHandles:
    browser: RetainedBrowserResource | None = None
    backend: NavigationBrowserDouble | None = None
    binding: TaskInitialBinding | None = None
    trace: Any = None
    completed: Any = None


class MapInitialSource(Protocol):
    @property
    def plans(self) -> RunPlans: ...
    @property
    def context(self) -> ContextAuthority: ...
    @property
    def source_ref(self) -> EvidenceRef: ...


def current_initial_binding(
    p: MapPreparationPortCase,
    journals: MapInitialSource,
    native: Any,
    handles: CurrentMapHandles,
    patch: pytest.MonkeyPatch,
    prep: RecordedSiteTaskPreparation,
    operation: OperationContext,
    control: OperationControl,
    *,
    negative: bool = False,
    page_type: type[Page] = Page,
) -> TaskInitialBinding:
    control.checkpoint()
    assert handles.browser is None and handles.backend is None
    assert prep is p.preparation
    state, c, n = prep.state, p.original, p.source.native
    assert isinstance(n, MapPreparation)
    assert state.result is not None and state.result_ref is not None
    assert state.prepare_request is not None and state.prepare_result is not None
    assert state.environment is not None
    n.request, n.result, n.environment = (
        state.prepare_request,
        state.prepare_result,
        state.environment,
    )
    base = configuration(c.configuration.installation)
    session = base.spec.model_copy(
        update={"scope": c.scope, "task": n.public, "max_events": 4096}
    )
    root = c.workspace / "current-initial-browser"
    root.mkdir()
    cfg, acquisition = declarations(
        n,
        p.site.site,
        state.result.publication,
        session,
        base,
        root,
        p.reset.attempt_allocations[0],
        started_ref=prep.state.original_acquired().site_started_ref,
    )
    # Expected action effects are private synthetic fixture setup, never Actor
    # input or a production dispatch. Reuse each original member's exact pin.
    original = json.loads(c.resource.evidence.read(c.private.native_contract_ref))
    target = original["control_target_path"]
    heading = re.sub(r"\\(.)", r"\1", original["completion"]["heading_regex"][1:-1])
    if negative:
        target, heading = "/about", "Wrong named document"

    def effect(page: Page, payload: str) -> None:
        assert payload == "click('a')"
        page.url = "/".join(page.url.split("/", 3)[:3]) + target
        page.headings = [heading]

    backend = navigation_browser_resource(
        root,
        patch,
        configuration=cfg,
        store=c.resource.evidence,
        declared_token=p.reset.attempt_allocations[0],
        site=c.resource.spec,
        public_text="RootWebArea 'Map navigation'\n  [a] link 'Requested local document'",
        step_effect=effect,
        page_type=page_type,
    )
    b = backend.resource
    closed_proof(browser_step, patch)
    b.op = acquisition.model_copy(
        update={"deadline": min(acquisition.deadline, p.plan.operation.deadline)}
    )
    # The declared original journal exists before this factory and has never
    # registered this browser. Do not replace any retained/started history.
    assert b.channels == [] and backend.engines == []
    b.journal = c.resource.journal
    prepared = PreparedBrowserBinding(
        state.result.publication,
        c.resource.spec,
        p.site.site,
        c.resource.op,
        evidence=c.resource.evidence,
        preparations=prep.records,
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
        authority=PreparedBrowserAuthority(b.spec, prepared, b.authority),
    )
    # Retain the original owner before any subsequent declaration can fail.
    handles.browser, handles.backend = browser, backend
    run = journals.plans.load(p.plan.intent.binding.run, p.plan.read_operation)
    assert isinstance(run.policies.actor_memory, InactivePolicy)
    role = next(role for role in run.models if role.role == "actor")
    parameters = (
        role.parameters_ref,
    ) * run.resources.max_actor_generations_per_attempt
    context = freeze_actor_context(
        native.scope.spec,
        parameters,
        native.policy,
        c.resource.evidence,
        soft_target=24576,
        control=control,
    )
    actor = TaskActorInitialization(
        candidate_id="original-candidate-0",
        revision_round=0,
        context_configuration_ref=put(c.resource.evidence, context),
        memory=run.policies.actor_memory,
        model_allocation=native.scope.binding.resource,
        parameters_refs=parameters,
        generation_seconds=60,
        interaction_seconds=30,
        cleanup_seconds=native.scope.binding.cleanup_seconds,
    )

    def phase(name: str) -> OperationContext:
        return p.plan.operation.model_copy(
            update={"operation_id": p.plan.operation.operation_id + ".initial-" + name}
        )

    d = TaskInitializationPlan(
        scope=c.scope,
        prepared_result_ref=state.result_ref,
        source_context_receipt_ref=journals.source_ref,
        browser_spec_ref=resource_put(
            b.evidence,
            b.spec.model_dump_json().encode(),
            b.spec.schema_version,
            b.controls.bind(b.op),
        ),
        browser_acquisition=b.op,
        capture_operation=b.op.model_copy(
            update={"operation_id": "current-initial-passive-capture"}
        ),
        initial_operation=phase("checks"),
        baseline_operation=phase("baseline"),
        comparison_operation=phase("compare"),
        equivalence_operation=phase("equivalence"),
        actor=actor,
    )
    result = TaskInitialBinding(
        d,
        put(c.resource.evidence, d),
        browser,
        journals.context,
        journals.context,
        UnitCaptureAuthority(p, browser),
        UnitInitialAuthority(),
    )
    handles.binding = result
    assert backend.engines == [] and browser.phase == "new"
    return result
