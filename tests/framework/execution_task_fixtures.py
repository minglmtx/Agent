"""Same execution loop + real actor-only source; all effects/rights unit-only."""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.plans.candidate_inputs import EvidenceCandidateInputs
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.actor.decisions import RecordedActorDecisions
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.application.actor_loop import RecordedActorRunner, ActorLoopDeps
from lab_generate_skill.application.execution_task_deps import (
    ExecutionTaskExecutionDeps,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRequirements
from lab_generate_skill.domain.lifecycle import ClosureReceipt, RecoveryPlan
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    InitializedTask,
    ClosedTaskResources,
)
from lab_generate_skill.domain.trace_plan import TracePlan, TraceCapacity
from actor_loop_fixtures import UnitAuthority, RunAuthority
from construction_storage_fixtures import put
from execution_task_source_fixtures import (
    source_case,
    SingleSourceCase,
    UnitExecutionAuthority,
)
from task_execution_fixtures import UnitPhases, UnitModel, UnitBrowser, UnitActorBinding
from task_execution_reset_fixtures import candidate_reset
from task_capture_actor_fixtures import controlled_context
from state_contract_fixtures import allocation
from test_run_journal import command


@dataclass
class ExecutionCase:
    source: SingleSourceCase
    plan: TaskExecutionPlan
    deps: ExecutionTaskExecutionDeps
    phases: UnitPhases
    authority: UnitExecutionAuthority
    model: UnitModel
    browser: UnitBrowser


def execution_case(root: Path) -> ExecutionCase:
    c = source_case(root)
    d, inputs, policy = c.data, c.inputs, c.policy
    store, controls = d.store, d.adapter.controls
    scope = inputs.candidate.scope
    phases = UnitPhases(c)
    browser_token = allocation("browser").model_copy(
        update={
            "owner": scope.owner,
            "attempt_id": scope.attempt_id,
            "recovery_ref": inputs.candidate_inputs.prepared.recovery_ref,
        }
    )
    reset = ResetPlan(
        scope=scope,
        parent_operation_id="task-original-prepare",
        spec_ref=inputs.candidate.spec_ref,
        task_recovery_ref=inputs.candidate_inputs.prepared.recovery_ref,
        environment_recovery_ref=inputs.source_inputs.reset_inputs.plan.environment_recovery_ref,
        attempt_allocations=(browser_token,),
    )
    reset_ref = put(store, reset, reset.schema_version)
    closure = ClosureReceipt(
        token=browser_token,
        operation_id="single-browser-closed",
        status="closed",
        evidence=(put(store, {"synthetic_termination": True}),),
    )
    closure_ref = put(store, closure, closure.schema_version)
    phases.closed = ClosedTaskResources(
        reset_plan=reset,
        reset_plan_ref=reset_ref,
        closures=(closure,),
        closure_refs=(closure_ref,),
    )
    phases.reset = candidate_reset(
        inputs, store, reset, reset_ref, closure, closure_ref
    )
    contract = EvaluationContract(
        identity=c.binding.task,
        attempt_id=c.binding.attempt_id,
        task_contract_ref=inputs.candidate_inputs.prepared.task_binding_ref,
        public_task_ref=c.source.task.public_task_ref,
        completion_spec_ref=put(store, {"unit_completion": True}),
        requirements=EvidenceRequirements(),
        scope="engineering",
    )
    op = command("original-single-task", attempt=scope.attempt_id)
    plan = TaskExecutionPlan(
        schema_version="task-execution-plan/2",
        intent=c.source.intent,
        source_ref=c.source_ref,
        reset_plan_ref=reset_ref,
        declaration_ref=put(store, {"unit_prepare": True}),
        skill_ref=c.skill_ref,
        evaluation=contract,
        operation=op,
        read_operation=command("single-independent-read"),
        cleanup_seconds=30,
    )
    request = ActorRunRequest(
        schema_version="actor-run-request/2",
        scope=scope,
        task=inputs.candidate_inputs.public_task,
        skill=policy.skill,
        memory=policy.memory,
        context_configuration_ref=policy.actor_context_ref,
        candidate_id=policy.candidate_id,
        revision_round=policy.revision_round,
        initial_observation_ref=inputs.candidate_inputs.observation_ref,
        model_allocation=allocation("actor", attempt=False).model_copy(
            update={
                "recovery_ref": put(
                    store,
                    RecoveryPlan(
                        recovery_id="unit-actor-close",
                        owner=scope.owner,
                        baseline_ref=inputs.candidate.spec_ref,
                        restore_component_id="unit-actor-close",
                        restore_component_version="1",
                        state_coverage=("unit-actor",),
                    ),
                    "recovery-plan/1",
                )
            }
        ),
        browser_allocation=browser_token,
        parameters_refs=(c.run.models[0].parameters_ref,),
        operation=op,
        generation_seconds=10,
        interaction_seconds=10,
        cleanup_seconds=15,
    )
    eq_ref = d.publish(d.comparison, d.comparison.operation)
    phases.initialized = InitializedTask(
        baseline_ref=inputs.candidate_ref, equivalence_ref=eq_ref, actor=request
    )
    traceplan = TracePlan(
        binding=c.binding,
        scope=scope,
        initial_observation_ref=request.initial_observation_ref,
        max_generations=1,
        max_interactions=1,
        capacity=TraceCapacity(
            max_events=128,
            max_bytes=2 * 1024**2,
            max_event_bytes=32768,
            max_trace_bytes=2 * 1024**2,
        ),
    )
    traceroot = root / "trace"
    traceroot.mkdir()
    journal = FileTraceJournal(traceroot, traceplan, controls, store, UnitAuthority())
    journal.create(traceplan, command("single-trace-created", attempt=scope.attempt_id))
    model = UnitModel(phases)
    browser = UnitBrowser(phases, journal)
    observations = EvidenceObservations(store, controls)
    runner = RecordedActorRunner(
        ActorLoopDeps(
            journal,
            store,
            observations,
            model,
            browser,
            RecordedActorDecisions(store, controls),
            prepare_actor,
            RunAuthority(),
            controls,
            SystemClock(),
            context=controlled_context(request, journal, store),
        )
    )
    actor = UnitActorBinding(runner, phases)
    states = EvidenceStateRecords(store, controls, d.authority)
    inputs_reader = EvidenceCandidateInputs(
        store, d.adapter, states, observations, controls
    )
    authority = UnitExecutionAuthority(phases)
    deps = ExecutionTaskExecutionDeps(
        c.source_reader,
        inputs_reader,
        c.claims,
        c.runs,
        phases,
        phases,
        actor,
        phases,
        phases,
        phases,
        states,
        authority,
        store,
        controls,
        SystemClock(),
    )
    return ExecutionCase(c, plan, deps, phases, authority, model, browser)
