"""Original ready preparation, sealed Actor, exact page and closed native guard."""

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.initial_observation import (
    InitialObservationSelection,
    InitialObservationInputs,
)
from lab_generate_skill.domain.task import PublicTask, TaskBinding
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.baseline import InitialStateChecks
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.run_plan import RunPlan, ExecutionWorkload
from lab_generate_skill.domain.actor_run import ActorRunRequest, ActorStop
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError, EvidenceNotFound
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.policies.evidence_bytes import (
    require_complete_bytes,
    require_complete_read_bound,
)
from lab_generate_skill.policies.sealed_browser_trace import (
    require_original_sealed_browser_trace,
    require_original_browser_actor_request,
)
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from lab_generate_skill.evaluators.browser_answer import trace_answer
from .navigation_evidence import CategoryNavigationEvidence
from .navigation_evidence_bodies import CategoryEvidenceBodies
from .tasks.navigation_binding import NativeCategoryLoader
from .tasks.navigation_spec import CategoryNavigationSpec
from .tasks.navigation_state_checks import CategoryNavigationStateChecks
from .tasks.navigation_recovery import CategoryNavigationRecoverySnapshot
from .tasks.navigation_state import CategoryNavigationState
from .tasks.navigation_admission import task_input, same_snapshot
from .tasks.navigation_initial_observation import (
    CategoryNavigationInitialObservationChecks,
)
from .tasks.navigation_page import CategoryNavigationPage

InitialLoader = Callable[
    [EvidenceReader, InitialObservationSelection, OperationControl],
    InitialObservationInputs,
]


@dataclass(frozen=True)
class CategoryNavigationFacts:
    public: PublicTask
    private: CategoryNavigationSpec
    page: CategoryNavigationPage
    site_origin: str


@dataclass(frozen=True)
class CategoryTerminalFacts:
    facts: CategoryNavigationFacts
    environment: EnvironmentSelection
    snapshot: CategoryNavigationRecoverySnapshot
    browser: BrowserResourceSpec
    page_operation_id: str
    return_operation_id: str


class CategoryNavigationEvaluationReads:
    def __init__(
        self,
        site: SiteResourceSpec,
        started: SiteResourceStarted,
        initial: InitialLoader,
        native: NativeCategoryLoader,
    ) -> None:
        self.site, self.started, self.initial, self.native = (
            site,
            started,
            initial,
            native,
        )

    def __call__(
        self,
        contract: EvaluationContract,
        selected: CategoryNavigationEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> CategoryNavigationFacts:
        bodies = CategoryEvidenceBodies(reader)
        try:
            return self._facts(contract, selected, bodies, control)
        finally:
            bodies.close()

    def _terminal(
        self,
        contract: EvaluationContract,
        selected: CategoryNavigationEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> CategoryTerminalFacts:
        if any(
            value is None
            for value in (
                selected.environment_ref,
                selected.initial,
                selected.initial_checks_ref,
                selected.trace_ref,
                selected.trace_snapshot_ref,
                selected.terminal_return_ref,
                selected.page,
            )
        ):
            raise EvidenceNotFound(
                "Original category environment/initial/trace/page missing"
            )
        assert (
            selected.environment_ref
            and selected.initial
            and selected.initial_checks_ref
        )
        assert (
            selected.trace_ref
            and selected.trace_snapshot_ref
            and selected.terminal_return_ref
        )
        assert selected.page
        reads = EvaluationEvidence(reader, control)
        binding = reads.read(contract.task_contract_ref, "task-binding/1", TaskBinding)
        public = reads.read(
            contract.public_task_ref, "public-task/1", PublicTask, public=True
        )
        private = reads.read(
            contract.completion_spec_ref,
            "shopping-category-navigation/1",
            CategoryNavigationSpec,
        )
        native_ref = private.native_contract_ref
        private_state_ref(native_ref, "shopping-native-contract/1")
        require_complete_read_bound(native_ref, 1024**2)
        if native_ref.media_type != "application/json":
            raise EvidenceIntegrityError("Original category native JSON required")
        control.checkpoint()
        native = reader.read(native_ref, control)
        require_complete_bytes(native_ref, native)
        control.checkpoint()
        if (
            (binding.identity, public.identity, private.task)
            != (contract.identity,) * 3
            or binding.public_task_ref != contract.public_task_ref
            or binding.private_spec_ref != contract.completion_spec_ref
            or self.native(native, native_ref, public).private_spec != private
        ):
            raise EvidenceIntegrityError(
                "Category judgment changed original native/public/private binding"
            )
        env = reads.read(
            selected.environment_ref, "environment-selection/1", EnvironmentSelection
        )
        states = CategoryNavigationStateChecks(reader)
        spec, site, snapshot = states._environment(env, control)
        if site != self.site or not isinstance(
            snapshot, CategoryNavigationRecoverySnapshot
        ):
            raise EvidenceIntegrityError(
                "Category judgment changed original environment/site"
            )
        initial = self.initial(reader, selected.initial, control)
        browser = initial.browser
        init = browser.configuration.initialization
        if (
            not isinstance(init, ShoppingCategoryInitialization)
            or initial.prepared.scope != env.scope
            or initial.prepared.scope.attempt_id != contract.attempt_id
            or initial.prepared.task_binding_ref != contract.task_contract_ref
            or initial.prepared.private_checks_ref != contract.completion_spec_ref
            or initial.prepared.public_task != public
            or env.spec_ref != binding.baseline_ref
            or initial.spec != spec
            or init.site_ref != env.site_started_ref
            or init.endpoint != self.started.instance.endpoint
            or init.native_contract_sha256 != native_ref.sha256
            or browser.slurm.execution != site.slurm.execution
            or browser.slurm.parent != site.slurm.parent
            or browser.configuration.installation != site.configuration.installation
        ):
            raise EvidenceIntegrityError(
                "Category judgment changed original prepared browser/attempt"
            )
        # The exact environment bytes also bind the actual started instance.
        if (
            reads.read(
                env.site_started_ref, "site-resource-started/1", SiteResourceStarted
            )
            != self.started
        ):
            raise EvidenceIntegrityError("Category started instance changed")
        first = reads.read(
            selected.initial_checks_ref, "initial-state-checks/1", InitialStateChecks
        )
        checks = CategoryNavigationInitialObservationChecks().check(initial, control)
        initial_ref = initial.acquired.details.started.initial_observation_ref
        if (
            first.scope != initial.prepared.scope
            or first.spec_ref != initial.prepared.spec_ref
            or first.prepared_ref != selected.initial.preparation.prepared_ref
            or first.observation_ref != initial_ref
            or first.measured_state_sha256 != initial_ref.sha256
            or first.checks != checks
            or checks.status != "pass"
            or first.operation.operation_id
            in (
                initial.returned.operation.operation_id,
                initial.acquired.operation.operation_id,
            )
        ):
            raise EvidenceIntegrityError(
                "Category unique original initial readiness changed"
            )
        trace = reads.read(
            selected.trace_ref,
            "interaction-trace/1",
            InteractionTrace,
            limit=16 * 1024**2,
        )
        journal = reads.read(
            selected.trace_snapshot_ref,
            "trace-journal-snapshot/1",
            TraceSnapshot,
            limit=16 * 1024**2,
        )
        run = reads.read(journal.plan.binding.run.plan_ref, "run-plan/3", RunPlan)
        require_original_sealed_browser_trace(run, journal, trace, initial)
        if (
            run.purpose != "engineering"
            or run.split != "train"
            or not isinstance(run.workload, ExecutionWorkload)
            or run.tasks != (binding,)
            or run.resources.max_parallel_tasks != 1
            or len(run.models) != 1
            or run.models[0].role != "actor"
            or run.models[0].paid
            or run.budget is not None
            or journal.plan.binding.run.release_ref
            != browser.configuration.installation.manifest_ref
        ):
            raise EvidenceIntegrityError(
                "Category Actor run lost original full binding/engineering/release"
            )
        stop = reads.read(trace.stop_evidence_ref, "trace-stop/1", ActorStop)
        actor = reads.read(
            stop.request_ref, stop.request_ref.content_schema, ActorRunRequest
        )
        if (
            actor.schema_version != "actor-run-request/2"
            or actor.schema_version != stop.request_ref.content_schema
        ):
            raise EvidenceIntegrityError(
                "Current original category Actor request required"
            )
        require_original_browser_actor_request(journal, trace, initial, stop, actor)
        trace_answer(trace, public, reads)
        terminal = reads.read(
            selected.terminal_return_ref,
            selected.terminal_return_ref.content_schema,
            BrowserReadout,
        )
        expected = initial.acquired.details.started.initial_return_ref
        for turn in trace.turns:
            event = turn.interaction
            if event is not None and event.result is not None:
                browser.check_operation(event.operation, "execute")
                expected = event.result.return_ref
        if (
            expected != selected.terminal_return_ref
            or terminal.scope != initial.prepared.scope
        ):
            raise EvidenceIntegrityError(
                "Category terminal is not original final Actor return"
            )
        browser.check_operation(terminal.operation, "execute")
        if terminal.observation.sequence == 0 and terminal != initial.returned:
            raise EvidenceIntegrityError(
                "Category changed original unique observation0"
            )
        intent = reads.read(
            selected.page.intent_ref, "browser-capture-intent/1", BrowserCaptureIntent
        )
        page_result = reads.read(
            selected.page.result_ref, "browser-capture-result/1", BrowserCaptureResult
        )
        request = intent.request
        browser.check_operation(request.operation, "execute")
        request.check_readout(browser.configuration.spec, terminal)
        if (
            (request.collector_id, request.collector_version)
            != ("shopping-category-navigation-page", "1")
            or intent.configuration_sha256
            != hashlib.sha256(
                browser.configuration.model_dump_json().encode()
            ).hexdigest()
            or page_result.request_sha256 != request.digest
            or page_result.captured_at < terminal.observation.captured_at
            or request.operation.operation_id
            in (
                terminal.operation.operation_id,
                initial.returned.operation.operation_id,
                initial.acquired.operation.operation_id,
            )
        ):
            raise EvidenceIntegrityError(
                "Category final page changed original browser/return/configuration"
            )
        page = CategoryNavigationPage.model_validate_json(page_result.private_result)
        if page.model_dump_json() != page_result.private_result:
            raise EvidenceIntegrityError("Noncanonical original category page")
        urls = [
            t.url
            for t in terminal.observation.tabs
            if t.tab_id == terminal.observation.active_tab_id
        ]
        if len(urls) != 1 or (
            page.health.status_source != "document_changed"
            and page.health.url != urls[0]
        ):
            raise EvidenceIntegrityError(
                "Category health changed original active document"
            )
        # DOM cannot grant the separate network-policy proof required by v3.
        if page.navigation_policy_block is not None:
            raise EvidenceIntegrityError(
                "Independent original category network-policy proof missing"
            )
        return CategoryTerminalFacts(
            CategoryNavigationFacts(public, private, page, init.endpoint),
            env,
            snapshot,
            browser,
            request.operation.operation_id,
            terminal.operation.operation_id,
        )

    def verify_terminal(
        self,
        contract: EvaluationContract,
        selected: CategoryNavigationEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> None:
        """Original pre-close facts only; no claim, closure or scored result."""
        bodies = CategoryEvidenceBodies(reader)
        try:
            self._terminal(contract, selected, bodies, control)
        finally:
            bodies.close()

    def _facts(
        self,
        contract: EvaluationContract,
        selected: CategoryNavigationEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> CategoryNavigationFacts:
        if any(
            value is None
            for value in (
                selected.environment_ref,
                selected.initial,
                selected.initial_checks_ref,
                selected.trace_ref,
                selected.trace_snapshot_ref,
                selected.terminal_return_ref,
                selected.page,
                selected.final_guard,
                selected.browser_closure_ref,
            )
        ):
            raise EvidenceNotFound(
                "Original category environment/initial/trace/page/closure/guard missing"
            )
        terminal = self._terminal(contract, selected, reader, control)
        env, snapshot, browser = (
            terminal.environment,
            terminal.snapshot,
            terminal.browser,
        )
        site, private = self.site, terminal.facts.private
        assert selected.final_guard and selected.browser_closure_ref
        reads = EvaluationEvidence(reader, control)
        closure = reads.read(
            selected.browser_closure_ref, "closure-receipt/1", ClosureReceipt
        )
        guard_intent = reads.read(
            selected.final_guard.intent_ref, "site-capture-intent/2", SiteCaptureIntent
        )
        guard_result = reads.read(
            selected.final_guard.result_ref, "site-task-result/1", SiteTaskResult
        )
        guard = guard_intent.request
        guard.check_site(site.configuration)
        same_snapshot(guard.inspection, snapshot, env.snapshot_ref)
        if (
            closure.token != browser.token
            or closure.status != "closed"
            or guard.inspection.operation.parent_operation_id != closure.operation_id
            or (guard.collector_id, guard.collector_version)
            != ("shopping-category-navigation", "1")
            or guard.selection_ref is not None
            or guard_intent.configuration_sha256
            != hashlib.sha256(site.configuration.model_dump_json().encode()).hexdigest()
            or guard_result.request_sha256 != guard.digest
            or task_input(guard.inspection).spec != private
            or guard.operation.operation_id
            in (
                snapshot.request.operation.operation_id,
                terminal.page_operation_id,
                terminal.return_operation_id,
            )
        ):
            raise EvidenceIntegrityError(
                "Category final native guard lost original closed browser/instance"
            )
        final = CategoryNavigationState.model_validate_json(guard_result.private_result)
        if (
            final.model_dump_json() != guard_result.private_result
            or final.task != contract.identity
            or final.protected != snapshot.protected
        ):
            raise EvidenceIntegrityError(
                "Complete original category native state changed; retain for review"
            )
        control.checkpoint()
        return terminal.facts
