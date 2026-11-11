"""Read original initial/Actor/native selections without model or site effects."""

from dataclasses import dataclass
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest, ActorStop
from lab_generate_skill.sites.shopping_admin.tasks.navigation_initial_capture import (
    require_navigation_initial_capture,
)
from lab_generate_skill.domain.baseline import InitialStateChecks
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.initial_observation import InitialObservationReads
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from lab_generate_skill.evaluators.browser_answer import trace_answer
from lab_generate_skill.evaluators.shopping_admin.navigation_evaluation_inputs import (
    load_navigation_facts,
)
from lab_generate_skill.policies.sealed_browser_trace import (
    require_original_sealed_browser_trace,
    require_original_browser_actor_request,
)
from lab_generate_skill.sites.shopping_admin.navigation_terminal_schema import (
    AdminNavigationTerminalSelection,
)
from lab_generate_skill.sites.shopping_admin.evidence_schema import (
    AdminNavigationEvidence,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_initial_observation import (
    NavigationInitialObservationChecks,
)


@dataclass(frozen=True)
class AdminNavigationTerminal:
    selection: AdminNavigationTerminalSelection
    initial: InitialObservationInputs
    returned: BrowserReadout
    selected: AdminNavigationEvidence
    preparation: SiteTaskRequest
    environment: EnvironmentSelection


def read_admin_navigation_terminal(
    store: EvidenceReader,
    preparations: PreparationRecords,
    reference: EvidenceRef,
    contract: EvaluationContract,
    operation: OperationContext,
    control: OperationControl,
    *,
    initials: InitialObservationReads | None = None,
) -> AdminNavigationTerminal:
    reads = EvaluationEvidence(store, control)
    selection = reads.read(
        reference,
        "admin-navigation-terminal-selection/1",
        AdminNavigationTerminalSelection,
    )
    selected_scope = selection.scope
    if (
        operation.run_id,
        operation.owner_id,
        operation.attempt_id,
        contract.identity,
        contract.attempt_id,
    ) != (
        selected_scope.owner.run_id,
        selected_scope.owner.owner_id,
        selected_scope.attempt_id,
        selected_scope.task,
        selected_scope.attempt_id,
    ):
        raise OwnershipConflict(
            "Original navigation terminal manifest identity required before dependencies"
        )
    reader = (
        InitialObservationReader(store, preparations) if initials is None else initials
    )
    initial = InitialObservationInputs.model_validate(
        reader.load(selection.initial, operation, control)
    )
    scope = initial.prepared.scope
    if (
        initial.selection != selection.initial
        or scope != selected_scope
        or (
            contract.identity,
            contract.attempt_id,
            contract.task_contract_ref,
            contract.completion_spec_ref,
        )
        != (
            scope.task,
            scope.attempt_id,
            initial.prepared.task_binding_ref,
            initial.prepared.private_checks_ref,
        )
    ):
        raise OwnershipConflict(
            "Original Admin navigation terminal scope/contract required"
        )
    first = reads.read(
        selection.initial_checks_ref, "initial-state-checks/1", InitialStateChecks
    )
    checks = NavigationInitialObservationChecks().check(initial, control)
    initial_ref = initial.acquired.details.started.initial_observation_ref
    if (
        first.scope,
        first.spec_ref,
        first.prepared_ref,
        first.observation_ref,
        first.measured_state_sha256,
        first.checks,
    ) != (
        scope,
        initial.prepared.spec_ref,
        selection.initial.preparation.prepared_ref,
        initial_ref,
        initial_ref.sha256,
        checks,
    ) or checks.status != "pass":
        raise EvidenceIntegrityError(
            "Navigation terminal lost original unique initial checks"
        )
    initial_intent = reads.read(
        selection.initial_capture_intent_ref,
        "browser-capture-intent/1",
        BrowserCaptureIntent,
    )
    initial_result = reads.read(
        selection.initial_capture_result_ref,
        "browser-capture-result/1",
        BrowserCaptureResult,
    )
    require_navigation_initial_capture(initial, initial_intent, initial_result)
    trace = reads.read(
        selection.trace_ref,
        "interaction-trace/1",
        InteractionTrace,
        limit=16 * 1024 * 1024,
    )
    snapshot = reads.read(
        selection.trace_snapshot_ref,
        "trace-journal-snapshot/1",
        TraceSnapshot,
        limit=16 * 1024 * 1024,
    )
    run = reads.read(snapshot.plan.binding.run.plan_ref, "run-plan/3", RunPlan)
    require_original_sealed_browser_trace(run, snapshot, trace, initial)
    stop = reads.read(trace.stop_evidence_ref, "trace-stop/1", ActorStop)
    actor = reads.read(
        stop.request_ref, stop.request_ref.content_schema, ActorRunRequest
    )
    if actor.schema_version != stop.request_ref.content_schema:
        raise EvidenceIntegrityError(
            "Navigation terminal changed original Actor request schema"
        )
    require_original_browser_actor_request(snapshot, trace, initial, stop, actor)
    trace_answer(trace, initial.prepared.public_task, reads)
    expected = initial.acquired.details.started.initial_return_ref
    for turn in trace.turns:
        if turn.interaction is not None:
            initial.browser.check_operation(turn.interaction.operation, "execute")
            if turn.interaction.result is None:
                raise EvidenceIntegrityError(
                    "Original navigation action return missing"
                )
            expected = turn.interaction.result.return_ref
    if selection.terminal_return_ref != expected:
        raise EvidenceIntegrityError(
            "Navigation terminal differs from original final return"
        )
    returned = reads.read(expected, expected.content_schema, BrowserReadout)
    final = reads.read(
        trace.final_observation_ref, "observation/1", Observation, public=True
    )
    if (
        returned.schema_version != expected.content_schema
        or returned.scope != scope
        or returned.observation != final
    ):
        raise EvidenceIntegrityError(
            "Navigation terminal changed original final observation"
        )
    selected = AdminNavigationEvidence(
        scope=scope,
        browser_spec_ref=selection.initial.browser_spec_ref,
        trace_ref=selection.trace_ref,
        page_intent_ref=selection.page_intent_ref,
        page_result_ref=selection.page_result_ref,
    )
    load_navigation_facts(contract, selected, reads)
    preparation = reads.read(
        selection.prepare_request_ref, "site-task-request/2", SiteTaskRequest
    )
    environment = reads.read(
        selection.environment_selection_ref,
        "environment-selection/1",
        EnvironmentSelection,
    )
    if (
        preparation.action != "prepare"
        or preparation.task != scope.task
        or preparation.binding_ref != initial.prepared.task_binding_ref
        or environment.scope != scope
        or environment.spec_ref != initial.prepared.spec_ref
        or environment.snapshot_ref != preparation.snapshot_ref
    ):
        raise EvidenceIntegrityError(
            "Navigation terminal changed original preparation/environment"
        )
    control.checkpoint()
    return AdminNavigationTerminal(
        selection, initial, returned, selected, preparation, environment
    )
