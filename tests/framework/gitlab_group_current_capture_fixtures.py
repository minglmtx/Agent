"""Group current chain with explicit SQL/page/model/kernel/permission doubles.

RPC, CAS, native snapshots, initial/baseline/equivalence, trace and cleanup
protocols are original code. These premises cannot qualify a deployed source.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import shutil

import pytest
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.resource_records import put as browser_put
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.adapters.sites.task_capture import RecordedTaskCapture
from lab_generate_skill.adapters.sites.task_site_capture_authority import (
    OriginalTaskSiteCaptureAuthority,
)
from lab_generate_skill.bootstrap.gitlab_group_browser_declarations import (
    group_browser_declaration,
)
from lab_generate_skill.bootstrap.gitlab_group_records import (
    group_prepared_browser_checks,
)
from lab_generate_skill.bootstrap.gitlab_group_task_capture import (
    gitlab_group_task_capture,
    CapturedGroupEvaluator,
)
from lab_generate_skill.bootstrap.gitlab_group_task_initialization import (
    gitlab_group_task_initialization,
    GroupTaskInitialization,
)
from lab_generate_skill.bootstrap.gitlab_group_task_preparation import (
    gitlab_group_task_preparation,
)
from lab_generate_skill.bootstrap.task_capture_inputs import (
    initialized_task_capture_inputs,
)
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureRequest,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    RecoveryPlan,
    ResourceRecord,
)
from lab_generate_skill.domain.optional_policies import InactivePolicy
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.task_capture import TaskCapturePlan
from lab_generate_skill.domain.task_execution import InitializedTask, TaskCaptureResult
from lab_generate_skill.domain.task_initialization import (
    TaskInitializationPlan,
    TaskActorInitialization,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.evaluators.gitlab.group import REQUIREMENTS
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.browser_capture import RawBrowserCapture
from lab_generate_skill.sites.gitlab.evidence_schema import GitlabPageHealth
from actor_context_projection_fixtures import actor_projection_case
from browser_resource_fixtures import resource_case as browser_case, ResourceCase
from browser_worker_fixtures import UnitBrowser, configuration
from context_budget_fixtures import profile
from gitlab_group_source_fixtures import group_source_unit_case
from gitlab_group_task_port_fixtures import GroupPortCase, group_port_case
from map_actor_trace_fixtures import execute_browser_actor
from preparation_record_fixtures import put
from retrieval_fixtures import reference
from task_capture_actor_fixtures import controlled_context
from task_capture_port_fixtures import UnitTaskCaptureAuthority
from task_initialization_port_fixtures import (
    UnitInitializationAuthority,
    UnitInitialAuthority,
    UnitNavigationContextAuthority,
)
from test_evidence_run_plans import persisted_plan, frozen_binding
from test_gitlab_group_source_composition import contracts_for
from test_gitlab_group_complete_starts import W
from test_resource_journal import context


class GroupPage(UnitBrowser):
    def __init__(self, config: BrowserWorkerConfiguration) -> None:
        super().__init__(config)
        self.last_capture: BrowserCaptureResult | None = None

    def capture_page(
        self, request: BrowserCaptureRequest, *, control: OperationControl
    ) -> BrowserCaptureResult:
        control.checkpoint()
        assert self.last_readout is not None
        request.check_readout(self.spec, self.last_readout)
        self.calls.append("passive-capture")
        self.last_capture = BrowserCaptureResult(
            request_sha256=request.digest,
            captured_at=datetime.now(timezone.utc),
            private_result=GitlabPageHealth(
                url=self.last_readout.observation.tabs[0].url,
                title="Page",
                http_status=200,
                status_source="navigation_timing",
                login_page=False,
                error_page=False,
                account_id=1,
            ).model_dump_json(),
        )
        return self.last_capture


class PagePermission:
    def __init__(self, browser: RetainedBrowserResource, backend: ResourceCase) -> None:
        self.browser, self.backend = browser, backend
        self.denied = False

    def verify_capture(
        self,
        configuration: BrowserWorkerConfiguration,
        request: BrowserCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert configuration == self.backend.spec.configuration
        intent = BrowserCaptureIntent.model_validate_json(
            self.backend.evidence.read(intent_ref, control)
        )
        assert intent.request == request
        assert (
            intent.configuration_sha256
            == hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
        )
        assert self.browser.session.observation_ref is not None
        assert request.observation_sha256 == self.browser.session.observation_ref.sha256
        if self.denied:
            raise PermissionError("Explicit synthetic Group page permission denied")


@dataclass
class CurrentGroupCase:
    preparation: GroupPortCase
    initialization: GroupTaskInitialization
    browser: RetainedBrowserResource
    backend: ResourceCase
    capture: RecordedTaskCapture
    evaluator: CapturedGroupEvaluator
    authority: UnitInitializationAuthority
    capture_authority: UnitTaskCaptureAuthority
    page_authority: PagePermission
    journals: list[FileTraceJournal] = field(default_factory=list)
    snapshot: TraceSnapshot | None = None

    def start(self) -> InitializedTask:
        p = self.preparation
        op = p.operation("starting")
        return self.initialization.start(p.plan, op, p.resource.controls.bind(op))

    def actor(self) -> TraceSnapshot:
        result = self.start()
        p = self.preparation
        _, _, _, self.snapshot = execute_browser_actor(
            p,
            self.backend,
            self.browser.session,
            terminal=True,
            request=result.actor,
            binding=p.plan.intent.binding,
            context_factory=lambda r, j: controlled_context(r, j, p.resource.evidence),
            on_journal=self.journals.append,
        )
        return self.snapshot

    def collect(self) -> TaskCaptureResult:
        assert self.snapshot is not None
        p = self.preparation
        op = p.operation("capture")
        return self.capture.capture(
            p.plan, self.snapshot, op, p.resource.controls.bind(op)
        )


@contextmanager
def current_group_case(
    root: Path, node: Path, patch: pytest.MonkeyPatch, source: str
) -> Iterator[CurrentGroupCase]:
    for child in (root / "source", root / "candidate"):
        child.mkdir(mode=0o700)
    import gitlab_group_fixtures as inputs

    patch.setattr(
        inputs,
        "FIXTURE",
        W
        / "experiments/sft-ordinary-source-bindings-v1/prepared/contracts"
        / (source + ".json"),
    )
    # Qualify the explicit synthetic source on a separate attempt/store, close
    # it once, then transport immutable bytes only. No source replay or grant.
    with pytest.MonkeyPatch.context() as source_patch:
        historical = group_source_unit_case(
            root / "source",
            node / "source",
            source_patch,
            contracts_for(source),
            "none",
        )
    with group_port_case(root / "candidate", node / "candidate", patch, source) as p:
        c, store = p.resource, p.resource.evidence
        for path in historical.site.evidence._blobs.iterdir():
            target = store._blobs / path.name
            if target.exists():
                assert target.read_bytes() == path.read_bytes()
            else:
                shutil.copyfile(path, target)
        assert historical.qualified is not None
        original_context = historical.qualified.receipt
        skill = CompactSkill.model_validate_json(store.read(p.plan.skill_ref))
        old = persisted_plan(store)
        run = RunPlan.model_validate(
            old.model_copy(
                update={
                    "tasks": (
                        old.tasks[0].model_copy(update={"identity": p.scope.task}),
                    ),
                    "resources": old.resources.model_copy(
                        update={
                            "max_actor_generations_per_attempt": 1,
                            "max_interactions_per_attempt": 1,
                        }
                    ),
                }
            )
        )
        bound = frozen_binding(store, run).model_copy(update={"owner": p.scope.owner})
        p.plan = p.plan.model_copy(
            update={
                "intent": p.plan.intent.model_copy(
                    update={
                        "binding": p.plan.intent.binding.model_copy(
                            update={
                                "run": bound,
                                "claim_ref": reference(
                                    {
                                        "explicit_synthetic_Group_source_permission": True
                                    },
                                    "source-claim/1",
                                    store=store,
                                ),
                            }
                        ),
                        "skill_digest": skill.content_digest,
                        "public_context_ref": original_context.public_context_ref,
                    }
                ),
                "evaluation": p.plan.evaluation.model_copy(
                    update={"requirements": REQUIREMENTS}
                ),
            }
        )
        p.preparation = gitlab_group_task_preparation(
            p.plan,
            p.declaration,
            c.spec,
            p.site,
            c.journal,
            store,
            c.controls,
            p.bindings,
            p.authority,
        )
        p.acquire()
        p.prepare()
        state = p.preparation.state
        assert state.result is not None and state.result_ref is not None
        prepared = p.preparation.records.load(
            state.result.publication, p.declaration.prepare_operation
        )
        base = configuration(c.spec.configuration.installation)
        cfg = BrowserWorkerConfiguration.model_validate(
            {
                **base.model_dump(),
                "spec": base.spec.model_copy(
                    update={
                        "scope": p.scope,
                        "task": prepared.public_task,
                        "max_events": 4096,
                    }
                ),
                "initialization": group_browser_declaration(
                    prepared.public_task,
                    p.site.site.instance.endpoint,
                    1,
                    state.result.publication.prepared_ref,
                    state.original_acquired().site_started_ref,
                ),
            }
        )
        patch.setattr("browser_resource_fixtures.UnitBrowser", GroupPage)
        assert isinstance(GroupPage(cfg), RawBrowserCapture)
        browser_root = root / "candidate-browser"
        browser_root.mkdir()
        b = browser_case(
            browser_root,
            patch,
            config=cfg,
            store=store,
            declared_token=p.reset.attempt_allocations[0],
        )
        b.spec = b.spec.model_copy(
            update={
                "slurm": b.spec.slurm.model_copy(
                    update={
                        "execution": c.spec.slurm.execution,
                        "parent": c.spec.slurm.parent,
                    }
                )
            }
        )
        b.op = context(b.spec.token, "acquire").model_copy(
            update={"deadline": p.plan.operation.deadline}
        )
        prepared_binding = PreparedBrowserBinding(
            state.result.publication,
            c.spec,
            p.site.site,
            c.op,
            evidence=store,
            preparations=p.preparation.records,
            journal=c.journal,
            task_checks=group_prepared_browser_checks(store),
        )
        browser = RetainedBrowserResource(
            b.spec,
            b.op,
            journal=b.journal,
            evidence=store,
            controls=b.controls,
            clock=b.clock,
            authority=PreparedBrowserAuthority(b.spec, prepared_binding, b.authority),
        )
        params = reference(
            LocalActorParameters(
                max_input_tokens=61440,
                max_new_tokens=4096,
                seed=0,
                temperature=0.0,
                top_p=1.0,
            ),
            "model-parameters/1",
            store=store,
        )
        actor_cfg = ActorContextConfiguration(
            policy=actor_projection_case(site="gitlab").policy,
            profiles=(
                profile(
                    provider="fixed-actor-worker",
                    configuration_ref=params,
                    context_window=65536,
                    output_reserve=4096,
                    input_limit=61440,
                    soft_target=24576,
                ),
            ),
        )
        recovery = RecoveryPlan(
            recovery_id="synthetic-actor-close",
            owner=p.scope.owner,
            baseline_ref=p.reset.spec_ref,
            restore_component_id="unit-actor-close",
            restore_component_version="1",
            state_coverage=("unit-actor",),
        )
        actor_token = AllocationToken(
            allocation_id="synthetic-actor",
            owner=p.scope.owner,
            scope="batch",
            resource_kind="actor",
            expected_resource_id="synthetic-actor",
            provider_id="fixed-actor-worker",
            provider_version="1",
            recovery_ref=put(store, recovery),
        )
        actor = TaskActorInitialization(
            candidate_id="candidate-zero",
            revision_round=0,
            context_configuration_ref=put(store, actor_cfg),
            memory=InactivePolicy(
                status="disabled", reason="explicit synthetic Group software fixture"
            ),
            model_allocation=actor_token,
            parameters_refs=(params,),
            generation_seconds=30,
            interaction_seconds=30,
            cleanup_seconds=30,
        )
        declaration = TaskInitializationPlan(
            scope=p.scope,
            prepared_result_ref=state.result_ref,
            source_context_receipt_ref=historical.qualified.material.context_ref,
            browser_spec_ref=browser_put(
                store,
                b.spec.model_dump_json().encode(),
                b.spec.schema_version,
                b.controls.bind(b.op),
            ),
            browser_acquisition=b.op,
            capture_operation=b.op.model_copy(
                update={"operation_id": "group-first-page"}
            ),
            initial_operation=p.operation("initial-checks"),
            baseline_operation=p.operation("baseline"),
            comparison_operation=p.operation("compare"),
            equivalence_operation=p.operation("equivalence"),
            actor=actor,
        )
        authority, contexts, page = (
            UnitInitializationAuthority(),
            UnitNavigationContextAuthority(),
            PagePermission(browser, b),
        )
        init = gitlab_group_task_initialization(
            p.plan,
            declaration,
            put(store, declaration),
            browser,
            p.preparation,
            authority,
            contexts,
            contexts,
            page,
            UnitInitialAuthority(),
            store,
            c.controls,
        )
        d = TaskCapturePlan(
            scope=p.scope,
            requirements=REQUIREMENTS,
            page_operation_id="group-last-page",
            close_operation_id="group-browser-close",
            guard_operation_id="group-final-native",
            page_collector_id="gitlab-page-health",
            page_collector_version="1",
            guard_collector_id="gitlab-group-creation",
            guard_collector_version="1",
            close_seconds=p.plan.cleanup_seconds,
        )
        journals: list[FileTraceJournal] = []
        capture_authority = UnitTaskCaptureAuthority()
        guard = OriginalTaskSiteCaptureAuthority(p.plan, p.preparation, lambda: capture)
        capture, evaluator = gitlab_group_task_capture(
            p.plan,
            d,
            put(store, d),
            lambda control: initialized_task_capture_inputs(
                p.preparation, init, control
            ),
            lambda: browser,
            lambda: journals[0],
            p.site,
            c.spec,
            p.preparation.records,
            lambda: init,
            capture_authority,
            page,
            guard,
            store,
            c.controls,
            c.clock,
        )

        def synthetic_physical(
            value: dict[str, Any],
            token: AllocationToken,
            evidence: Any,
            control: OperationControl,
        ) -> dict[str, Any]:
            # Only the unavailable original worker/kernel proof is a premise.
            # Original acquisition/fact/closure links remain production checks.
            record = ResourceRecord.model_validate_json(json.dumps(value))
            assert record.token == token and record.state == "closed"
            acquisition = ResourceAcquisitionIntent.model_validate_json(
                evidence.read(record.events[1].evidence[0], control)
            )
            ending = json.loads(evidence.read(record.events[-1].evidence[0], control))[
                "details"
            ]
            return {
                "configuration": json.loads(
                    evidence.read(acquisition.configuration_ref, control)
                ),
                "ending": ending,
            }

        patch.setattr(
            "lab_generate_skill.bootstrap.gitlab_group_captured.review_resource",
            synthetic_physical,
        )
        try:
            capture.preflight(
                p.plan,
                evaluator.requirements(p.plan.evaluation),
                c.controls.bind(p.plan.operation),
            )
            assert (
                browser.phase == "new"
                and not journals
                and not init.native_before.attempted
            )
            yield CurrentGroupCase(
                p,
                init,
                browser,
                b,
                capture,
                evaluator,
                authority,
                capture_authority,
                page,
                journals,
            )
        finally:
            if browser.phase == "open":
                op = b.op.cleanup(
                    "synthetic-group-browser-close", now=b.clock.utcnow(), seconds=30
                )
                browser.close(op, b.controls.bind(op))
