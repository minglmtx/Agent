"""Full-policy native/Actor2/capture combination with explicit unit permissions.

Real record, wire, trace and native restore algorithms run on synthetic services,
model/page/kernel facts. Baseline/equivalence dispatch rights are explicit unit
premises; this fixture cannot qualify an actual source or default production run.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.adapters.browsergym.recorded_capture import (
    RecordedBrowserCapture,
)
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.bootstrap.admin_navigation import (
    admin_navigation_preparation_records,
    admin_navigation_initial_observations,
)
from lab_generate_skill.bootstrap.admin_navigation_task_capture import (
    admin_navigation_task_capture,
    CapturedAdminNavigationEvaluator,
)
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_capture import BrowserCaptureRequest
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.preparation_record import PreparationSelection
from lab_generate_skill.domain.task_intent import TaskAttemptIntent
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.task_capture import TaskCapturePlan, TaskCaptureInputs
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.site_capture import SiteCaptureRequest, SiteCaptureIntent
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.tasks.navigation_prepared_browser import (
    NavigationPreparedBrowserChecks,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationExecutionInput,
)
from lab_generate_skill.evaluators.shopping_admin.navigation import REQUIREMENTS
from admin_navigation_state_fixtures import qualified
from admin_navigation_initial_fixtures import Authority as InitialAuthority
from admin_navigation_terminal_fixtures import ActorCase, install_navigation_browser
from admin_navigation_actor_fixtures import current_actor
from browser_resource_fixtures import resource_case
from browser_worker_fixtures import configuration
from task_capture_actor_fixtures import controlled_context
from task_capture_port_fixtures import UnitTaskCaptureAuthority
from map_actor_trace_fixtures import execute_browser_actor
from preparation_record_fixtures import Authority, put
from retrieval_fixtures import reference
from test_browser_capture import Authority as BrowserCaptureAuthority


@dataclass
class CaptureCase:
    qualified: dict[str, Any]
    browser: RetainedBrowserResource
    capture: Any
    evaluator: CapturedAdminNavigationEvaluator
    plan: TaskExecutionPlan
    authority: UnitTaskCaptureAuthority
    site_authority: Any
    snapshot: Any

    def collect(self) -> Any:
        return self.capture.capture(
            self.plan,
            self.snapshot,
            self.plan.operation,
            self.qualified["c"].controls.bind(self.plan.operation),
        )


@contextmanager
def capture_case(
    root: Path,
    node: Path,
    patch: pytest.MonkeyPatch,
    contracts: Any,
    *,
    negative: bool = False,
) -> Iterator[CaptureCase]:
    site_root = root / "site"
    site_root.mkdir()
    with qualified(site_root, node, patch, contracts, before_restore=True) as q:
        c, store, live = q["c"], q["store"], q["live"]
        prep_rights = Authority()
        preparations = admin_navigation_preparation_records(
            store,
            c.controls,
            EvidenceTaskBindings(store, c.controls, prep_rights),
            prep_rights,
        )
        prepare_ref = put(store, q["prepare"])
        selected = PreparationSelection(
            request_ref=prepare_ref,
            result_ref=put(store, q["prepared_result"]),
            environment_ref=q["environment_ref"],
        )
        publication = preparations.publish(selected, q["prepare"].operation)
        prepared = preparations.load(publication, q["prepare"].operation)
        base = configuration(c.spec.configuration.installation)
        private = NavigationExecutionInput.model_validate_json(
            q["prepare"].private_input
        ).spec
        cfg = BrowserWorkerConfiguration.model_validate(
            {
                **base.model_dump(),
                "spec": BrowserSessionSpec.model_validate(
                    {
                        **base.spec.model_dump(),
                        "scope": prepared.scope,
                        "task": prepared.public_task,
                    }
                ),
                "initialization": AdminNavigationInitialization(
                    endpoint=live.site.instance.endpoint,
                    prepared_ref=publication.prepared_ref,
                    site_ref=q["environment"].site_started_ref,
                    native_contract_sha256=private.native_contract_ref.sha256,
                    start_path=private.start_path,
                ),
            }
        )
        browser_root = root / "browser"
        browser_root.mkdir()
        install_navigation_browser(patch, contracts[0][0], negative)
        b = resource_case(
            browser_root,
            patch,
            config=cfg,
            store=store,
            declared_token=q["plan"].attempt_allocations[0],
        )
        binding = PreparedBrowserBinding(
            publication,
            c.spec,
            live.site,
            c.op,
            evidence=store,
            preparations=preparations,
            journal=c.journal,
            task_checks=NavigationPreparedBrowserChecks(),
        )
        browser = RetainedBrowserResource(
            b.spec,
            b.op,
            journal=b.journal,
            evidence=store,
            controls=b.controls,
            clock=b.clock,
            authority=PreparedBrowserAuthority(b.spec, binding, b.authority),
        )
        with browser as session:
            acquisition = ResourceAcquisitionIntent.model_validate_json(
                store.read(b.journal.read(b.spec.token, b.op).events[1].evidence[0])
            )
            assert session.resource_started_ref is not None
            initial = InitialObservationSelection(
                preparation=publication,
                browser_spec_ref=acquisition.configuration_ref,
                browser_acquired_ref=session.resource_started_ref,
            )
            initial_op = b.op.model_copy(
                update={"operation_id": "admin.initial-checks"}
            )
            initial_records = admin_navigation_initial_observations(
                store, c.controls, preparations, InitialAuthority(initial)
            )
            initial_ref = initial_records.publish(initial, initial_op)
            assert isinstance(session.engine, SupervisedBrowserSession)
            assert session.observation_ref is not None
            page = RecordedBrowserCapture(
                session.engine, store, BrowserCaptureAuthority(store)
            )
            capture_op = b.op.model_copy(update={"operation_id": "admin.initial-page"})
            page_ref = page.capture(
                BrowserCaptureRequest(
                    scope=prepared.scope,
                    operation=capture_op,
                    observation_sha256=session.observation_ref.sha256,
                    collector_id="admin-navigation-page",
                    collector_version="1",
                ),
                control=c.controls.bind(capture_op),
            )
            assert page.intent_ref is not None
            case = ActorCase(c, prepared.scope, root, prepared.task_binding_ref)
            request, attempt = current_actor(case, b, session, store)
            journals: list[FileTraceJournal] = []
            _, _, _, snapshot = execute_browser_actor(
                case,
                b,
                session,
                request=request,
                binding=attempt,
                context_factory=lambda r, j: controlled_context(r, j, store),
                on_journal=journals.append,
            )
            contract = EvaluationContract(
                identity=prepared.scope.task,
                attempt_id=prepared.scope.attempt_id,
                task_contract_ref=prepared.task_binding_ref,
                public_task_ref=q["binding"].public_task_ref,
                completion_spec_ref=prepared.private_checks_ref,
                requirements=REQUIREMENTS,
                scope="engineering",
            )
            plan = TaskExecutionPlan(
                intent=TaskAttemptIntent(
                    binding=attempt,
                    candidate_slot=0,
                    skill_digest=request.skill.content_digest,
                    public_context_ref=reference(
                        {"unit_source_only": True},
                        "public-construction-context/1",
                        visibility="public",
                        store=store,
                    ),
                ),
                reset_plan_ref=q["plan_ref"],
                declaration_ref=prepare_ref,
                skill_ref=put(store, request.skill, "public"),
                evaluation=contract,
                operation=request.operation,
                read_operation=request.operation.model_copy(
                    update={"operation_id": "admin.run-read", "attempt_id": None}
                ),
                cleanup_seconds=60,
            )
            inputs = TaskCaptureInputs(
                initialized=InitializedTask(
                    baseline_ref=reference(
                        {"unit_dispatch_baseline": True},
                        "baseline-receipt/1",
                        store=store,
                    ),
                    equivalence_ref=reference(
                        {"unit_dispatch_equivalence": True},
                        "equivalence-receipt/1",
                        store=store,
                    ),
                    actor=request,
                ),
                initial=initial,
                initial_checks_ref=initial_ref,
                initial_capture_intent_ref=page.intent_ref,
                initial_capture_result_ref=page_ref,
                environment_selection_ref=q["selection_ref"],
                prepare_request_ref=prepare_ref,
            )
            declaration = TaskCapturePlan(
                schema_version="task-capture-plan/2",
                metadata_close_seconds=60,
                scope=prepared.scope,
                requirements=REQUIREMENTS,
                page_operation_id="admin.final-page",
                close_operation_id="admin.capture-close",
                guard_operation_id="admin.complete-guard",
                page_collector_id="admin-navigation-page",
                page_collector_version="1",
                guard_collector_id="admin-navigation-snapshot-integrity",
                guard_collector_version="1",
                close_seconds=30,
            )
            rights = UnitTaskCaptureAuthority()

            class SiteCaptureAuthority:
                calls = 0

                def verify_capture(
                    self,
                    configuration: SiteWorkerConfiguration,
                    request: SiteCaptureRequest,
                    intent_ref: EvidenceRef,
                    control: OperationControl,
                ) -> None:
                    control.checkpoint()
                    intent = SiteCaptureIntent.model_validate_json(
                        store.read(intent_ref, control)
                    )
                    assert (
                        configuration == c.spec.configuration
                        and intent.request == request
                    )
                    assert (
                        browser.phase == "closed"
                        and request.inspection.snapshot_ref == q["snapshot_ref"]
                    )
                    self.calls += 1

            site_rights = SiteCaptureAuthority()
            # The fixed wire calls the original navigation integrity algorithm;
            # only native services/kernel/dispatch permission remain explicit doubles.
            patch.setattr(
                c.channels[0].engine,
                "capture_task",
                q["worker"].capture_task,
                raising=False,
            )
            capture, evaluator = admin_navigation_task_capture(
                plan,
                declaration,
                put(store, declaration),
                lambda control: inputs,
                lambda: browser,
                lambda: journals[0],
                live,
                c.spec,
                preparations,
                rights,
                BrowserCaptureAuthority(store),
                site_rights,
                store,
                c.controls,
                c.clock,
            )
            capture.preflight(plan, REQUIREMENTS, c.controls.bind(plan.operation))
            yield CaptureCase(
                q, browser, capture, evaluator, plan, rights, site_rights, snapshot
            )
