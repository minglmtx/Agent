"""Reconstruct original Group initial/native/Actor/page facts without effects."""

from dataclasses import dataclass
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.domain.actor_run import ActorRunRequest, ActorStop
from lab_generate_skill.domain.baseline import InitialStateChecks, BaselineReceipt
from lab_generate_skill.domain.browser_capture import BrowserCaptureIntent
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.initial_equivalence import EquivalenceReceipt
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.task_capture import TaskCapturePlan
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from lab_generate_skill.evaluators.browser_answer import trace_answer
from lab_generate_skill.policies.sealed_browser_trace import (
    require_original_sealed_browser_trace,
    require_original_browser_actor_request,
)
from lab_generate_skill.sites.gitlab.group_terminal_schema import GroupTerminalSelection
from lab_generate_skill.sites.gitlab.evaluation_context import (
    read_context,
    check_context,
    final_page,
)
from lab_generate_skill.sites.gitlab.tasks.group_environment import (
    GroupEnvironmentChecks,
)
from lab_generate_skill.sites.gitlab.tasks.group_initial_capture import (
    GroupTaskInitialChecks,
)
from lab_generate_skill.sites.gitlab.tasks.group_recovery import GroupRecoverySnapshot
from .gitlab_group_capture import load_group_capture


@dataclass(frozen=True)
class GroupTerminal:
    selection: GroupTerminalSelection
    initial: InitialObservationInputs
    preparation: SiteTaskRequest
    environment: EnvironmentSelection
    trace: InteractionTrace
    declaration: TaskInitializationPlan
    capture_plan: TaskCapturePlan
    snapshot: GroupRecoverySnapshot


def read_group_terminal(
    store: EvidenceReader,
    preparations: PreparationRecords,
    reference: EvidenceRef,
    contract: EvaluationContract,
    operation: OperationContext,
    control: OperationControl,
) -> GroupTerminal:
    reads = EvaluationEvidence(store, control)
    selected = reads.read(
        reference, "gitlab-group-terminal-selection/1", GroupTerminalSelection
    )
    scope = selected.scope
    if (
        operation.run_id,
        operation.owner_id,
        operation.attempt_id,
        contract.identity,
        contract.attempt_id,
    ) != (
        scope.owner.run_id,
        scope.owner.owner_id,
        scope.attempt_id,
        scope.task,
        scope.attempt_id,
    ):
        raise OwnershipConflict(
            "Original Group terminal scope required before dependencies"
        )
    initial = InitialObservationReader(store, preparations).load(
        selected.initial, operation, control
    )
    declaration = reads.read(
        selected.initialization_plan_ref,
        "task-initialization-plan/2",
        TaskInitializationPlan,
    )
    capture_plan = reads.read(
        selected.capture_plan_ref,
        selected.capture_plan_ref.content_schema,
        TaskCapturePlan,
    )
    if (capture_plan.scope, capture_plan.requirements) != (
        scope,
        contract.requirements,
    ) or (
        capture_plan.page_collector_id,
        capture_plan.page_collector_version,
        capture_plan.guard_collector_id,
        capture_plan.guard_collector_version,
    ) != (
        "gitlab-page-health",
        "1",
        "gitlab-group-creation",
        "1",
    ):
        raise EvidenceIntegrityError(
            "Original Group capture declaration/collectors required"
        )
    first = reads.read(
        selected.initial_checks_ref, "initial-state-checks/1", InitialStateChecks
    )
    checks = GroupTaskInitialChecks(
        store,
        declaration,
        selected.initial_page.intent_ref,
        selected.initial_page.result_ref,
        selected.before,
        load_group_capture,
    ).check(initial, control)
    initial_ref = initial.acquired.details.started.initial_observation_ref
    if (
        first.scope,
        first.spec_ref,
        first.prepared_ref,
        first.observation_ref,
        first.operation,
        first.measured_state_sha256,
        first.checks,
    ) != (
        scope,
        initial.prepared.spec_ref,
        selected.initial.preparation.prepared_ref,
        initial_ref,
        declaration.initial_operation,
        initial_ref.sha256,
        checks,
    ) or checks.status != "pass":
        raise EvidenceIntegrityError(
            "Group terminal lost original initial page/native checks"
        )
    if (
        contract.task_contract_ref,
        contract.completion_spec_ref,
        initial.prepared.scope,
    ) != (
        initial.prepared.task_binding_ref,
        initial.prepared.private_checks_ref,
        scope,
    ):
        raise OwnershipConflict("Group terminal changed original task contract")
    initialized = selected.initialized
    baseline = reads.read(
        initialized.baseline_ref, "baseline-receipt/1", BaselineReceipt
    )
    baseline_inputs = BaselineEvidenceReader(store).verify(baseline, control)
    equivalence = reads.read(
        initialized.equivalence_ref, "equivalence-receipt/1", EquivalenceReceipt
    )
    if (
        baseline.status != "ready"
        or baseline.scope != scope
        or baseline.initial_checks_ref != selected.initial_checks_ref
        or baseline.operation != declaration.baseline_operation
        or baseline_inputs.initial != first
        or equivalence.scope != scope
        or equivalence.status != "equivalent"
        or equivalence.candidate_baseline_ref != initialized.baseline_ref
        or equivalence.source_context_receipt_ref
        != declaration.source_context_receipt_ref
        or equivalence.operation != declaration.equivalence_operation
    ):
        raise EvidenceIntegrityError(
            "Group terminal lost original baseline/equivalence links"
        )
    trace = reads.read(
        selected.trace_ref, "interaction-trace/1", InteractionTrace, limit=16 * 1024**2
    )
    snapshot = reads.read(
        selected.trace_snapshot_ref,
        "trace-journal-snapshot/1",
        TraceSnapshot,
        limit=16 * 1024**2,
    )
    run = reads.read(snapshot.plan.binding.run.plan_ref, "run-plan/3", RunPlan)
    require_original_sealed_browser_trace(run, snapshot, trace, initial)
    stop = reads.read(trace.stop_evidence_ref, "trace-stop/1", ActorStop)
    actor = reads.read(
        stop.request_ref, stop.request_ref.content_schema, ActorRunRequest
    )
    require_original_browser_actor_request(snapshot, trace, initial, stop, actor)
    if actor != initialized.actor:
        raise EvidenceIntegrityError(
            "Group terminal replaced original initialized Actor"
        )
    trace_answer(trace, initial.prepared.public_task, reads)
    expected = initial.acquired.details.started.initial_return_ref
    for turn in trace.turns:
        if turn.interaction is not None:
            initial.browser.check_operation(turn.interaction.operation, "execute")
            if turn.interaction.result is None:
                raise EvidenceIntegrityError("Original Group action return missing")
            expected = turn.interaction.result.return_ref
    if selected.terminal_return_ref != expected:
        raise EvidenceIntegrityError("Group terminal changed original last return")
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
            "Group terminal changed original final observation"
        )
    prepare = reads.read(
        selected.prepare_request_ref, "site-task-request/2", SiteTaskRequest
    )
    environment = reads.read(
        selected.environment_selection_ref,
        "environment-selection/1",
        EnvironmentSelection,
    )
    native = GroupEnvironmentChecks(store, load_group_capture)
    context = read_context(
        native,
        contract,
        selected.environment_selection_ref,
        selected.initial.browser_spec_ref,
        selected.trace_ref,
        control,
    )
    _, site, saved = native._environment(environment, control)
    check_context(
        native,
        contract,
        context,
        site,
        saved.native_before.context.instance.endpoint,
        "gitlab_group_creation",
        control,
    )
    if (
        prepare.action != "prepare"
        or prepare.binding_ref != contract.task_contract_ref
        or (environment.scope, environment.snapshot_ref, environment.spec_ref)
        != (scope, prepare.snapshot_ref, initial.prepared.spec_ref)
    ):
        raise EvidenceIntegrityError("Group terminal changed preparation/environment")
    page = reads.read(
        selected.page.intent_ref, "browser-capture-intent/1", BrowserCaptureIntent
    )
    if page.request.operation.operation_id != capture_plan.page_operation_id:
        raise EvidenceIntegrityError("Group terminal changed declared page operation")
    final_page(native, context, selected.page, control)
    return GroupTerminal(
        selected, initial, prepare, environment, trace, declaration, capture_plan, saved
    )
