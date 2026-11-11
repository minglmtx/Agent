"""Real journals/admission/Actor loop/CAS; synthetic website/model/closure facts.

This is the lifecycle module gate, not real source or compression quality proof.
"""

from typing import Protocol
import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.actor.decisions import RecordedActorDecisions
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.application.actor_loop import RecordedActorRunner, ActorLoopDeps
from lab_generate_skill.application.construction_task_deps import (
    ConstructionTaskExecutionDeps as TaskExecutionDeps,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.actor_generation import ActorGeneration
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.browser import BrowserAction, StepResult
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.evaluation import (
    Evaluation,
    EvaluationContract,
    CheckResult,
)
from lab_generate_skill.domain.evidence import EvidenceRequirements, EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    ClosureReceipt,
    RecoveryPlan,
)
from lab_generate_skill.domain.optional_policies import InactivePolicy
from lab_generate_skill.domain.reset import (
    ResetPlan,
    ResetReceipt,
    ResetInputs,
    TaskResetReceipt,
    EnvironmentResetReceipt,
    ResetHealthReceipt,
    assemble_reset,
)
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    InitializedTask,
    ClosedTaskResources,
    TaskCaptureResult,
)
from lab_generate_skill.domain.trace_events import GenerationIntent
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_plan import TracePlan, TraceCapacity
from lab_generate_skill.ports.actor import ActorRunner
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.state_records import StateRecords
from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.initial_equivalence import EquivalenceInputs
from evidence_control_fixtures import EvidenceFixtureStore
from actor_admission_fixtures import fixture, AdmissionFixture
from actor_loop_fixtures import UnitAuthority, RunAuthority
from construction_storage_fixtures import put
from test_run_journal import Harness, command, CancelSwitch
from state_contract_fixtures import allocation
from lab_generate_skill.runtime.lifecycle import OperationGuards


class UnitPhaseData(Protocol):
    @property
    def store(self) -> EvidenceFixtureStore: ...


class UnitPhaseContext(Protocol):
    @property
    def data(self) -> UnitPhaseData: ...
    @property
    def inputs(self) -> EquivalenceInputs: ...


class UnitPhases:
    def __init__(self, admission: UnitPhaseContext) -> None:
        self.admission = admission
        self.calls: list[str] = []
        self.errors: dict[str, BaseException] = {}
        self.initialized: InitializedTask
        self.closed: ClosedTaskResources
        self.reset: ResetReceipt
        self.denied = False
        self.closure_denied = False
        self.evaluation_status = "failure"

    def hit(self, name: str, control: OperationControl) -> None:
        control.checkpoint()
        self.calls.append(name)
        if name in self.errors:
            raise self.errors[name]

    def acquire(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> tuple[EvidenceRef, ...]:
        self.hit("acquire", control)
        return (plan.declaration_ref,)

    def prepare(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> tuple[EvidenceRef, ...]:
        self.hit("prepare", control)
        return (plan.declaration_ref,)

    def start(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> InitializedTask:
        self.hit("start", control)
        return self.initialized

    def preflight(
        self,
        plan: TaskExecutionPlan,
        requirements: EvidenceRequirements,
        control: OperationControl,
    ) -> None:
        self.hit("preflight", control)
        assert requirements == plan.evaluation.requirements

    def capture(
        self,
        plan: TaskExecutionPlan,
        snapshot: TraceSnapshot,
        operation: OperationContext,
        control: OperationControl,
    ) -> TaskCaptureResult:
        self.hit("capture", control)
        assert snapshot.project().sealed is not None
        return TaskCaptureResult(
            contract=plan.evaluation, references=(plan.declaration_ref,)
        )

    def requirements(self, contract: EvaluationContract) -> EvidenceRequirements:
        return contract.requirements

    def evaluate(
        self, contract: EvaluationContract, evidence: object, control: OperationControl
    ) -> Evaluation:
        self.hit("evaluate", control)
        check = CheckResult(
            name="original-goal",
            status=(
                "pass"
                if self.evaluation_status == "success"
                else ("unknown" if self.evaluation_status == "unknown" else "fail")
            ),
            reason_code="unit-native-judgment",
            evidence=(contract.task_contract_ref,),
        )
        return Evaluation.model_validate(
            dict(
                identity=contract.identity,
                attempt_id=contract.attempt_id,
                contract_ref=contract.task_contract_ref,
                evaluator_id="unit-task",
                evaluator_version="1",
                status=self.evaluation_status,
                reward={"success": 1, "failure": 0, "unknown": None}[
                    self.evaluation_status
                ],
                checks=(check,),
                reason_code="unit-native-judgment",
            )
        )

    def close(
        self,
        plan: TaskExecutionPlan,
        reset: ResetPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosedTaskResources:
        self.hit("close", control)
        assert reset == self.closed.reset_plan
        return self.closed

    def restore(
        self,
        plan: TaskExecutionPlan,
        closed: ClosedTaskResources,
        operation: OperationContext,
        control: OperationControl,
    ) -> EvidenceRef:
        self.hit("restore", control)
        assert closed == self.closed
        return put(self.admission.data.store, self.reset, "reset-receipt/1")

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
            raise PermissionError("unit task source denied")
        assert (
            plan.intent == progress.project().pending_attempt
            and reset == self.closed.reset_plan
        )

    def verify_closed(
        self,
        plan: TaskExecutionPlan,
        closed: ClosedTaskResources,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self.hit("verify_closed", control)
        if self.closure_denied:
            raise PermissionError("unit original termination unconfirmed")
        assert closed == self.closed


class UnitModel:
    def __init__(self, phases: UnitPhases) -> None:
        self.phases = phases
        self.calls = 0

    def validate(self, intent: GenerationIntent, *, control: OperationControl) -> None:
        control.checkpoint()

    def generate(
        self, intent: GenerationIntent, *, control: OperationControl
    ) -> ActorGeneration:
        self.phases.hit("model", control)
        self.calls += 1
        store = self.phases.admission.data.store
        prompt = ActorPrompt.model_validate_json(store.read(intent.input_ref))
        completion = ActorTextCompletion(
            generation_id=intent.generation_id,
            request_id=intent.request_id,
            input_ref=intent.input_ref,
            model_input_sha256=hashlib.sha256(prompt.input_bytes()).hexdigest(),
            parameters_ref=intent.parameters_ref,
            text='{"action":"send_msg_to_user(\'Done\')"}',
            finish_reason="stop",
        )
        ref = put(store, completion, "actor-model-response/1")
        return ActorGeneration.model_validate(
            {
                **intent.model_dump(exclude={"schema_version"}),
                "schema_version": (
                    "actor-generation/2"
                    if intent.schema_version == "actor-generation-intent/2"
                    else "actor-generation/1"
                ),
                "status": "completed",
                "response_ref": ref,
                "failure_ref": None,
            }
        )


class UnitBrowser:
    def __init__(self, phases: UnitPhases, journal: FileTraceJournal) -> None:
        self.phases, self.journal = phases, journal
        self.calls = 0

    def step(
        self,
        action: BrowserAction,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> StepResult:
        self.phases.hit("browser", control)
        self.calls += 1
        c = self.phases.admission
        snapshot = self.journal.read(command(attempt=operation.attempt_id))
        before = snapshot.project().current_observation(snapshot.plan)
        old = c.inputs.candidate_inputs.observation
        observed = old.model_copy(
            update={"observation_id": "task-final-observation", "sequence": 1}
        )
        after = put(c.data.store, observed, "observation/1", "public")
        raw = put(
            c.data.store, {"action_id": action.action_id}, "browser-step-return/1"
        )
        return StepResult(
            scope=snapshot.plan.scope,
            operation=operation,
            action_id=action.action_id,
            before_observation_ref=before,
            observation_ref=after,
            return_ref=raw,
            terminal=True,
        )


class UnitActorBinding:
    def __init__(self, runner: RecordedActorRunner, phases: UnitPhases) -> None:
        self.runner, self.phases = runner, phases
        self.calls = 0

    def bind(
        self, initialized: InitializedTask, prepared: PreparedActorInput
    ) -> ActorRunner:
        assert initialized.actor.skill == prepared.actor_input.skill
        self.calls += 1
        self.phases.calls.append("bind_actor")
        return self.runner


@dataclass
class TaskCase:
    admission: AdmissionFixture
    plan: TaskExecutionPlan
    deps: TaskExecutionDeps
    phases: UnitPhases
    model: UnitModel
    browser: UnitBrowser
    actor: UnitActorBinding


def task_case(
    root: Path,
    *,
    admitted: AdmissionFixture | None = None,
    shared_run: TaskCase | None = None,
) -> TaskCase:
    root.mkdir(exist_ok=admitted is not None)
    c = (
        fixture(root, stage="planned", allowed_actions=("send_msg_to_user",))
        if admitted is None
        else admitted
    )
    d = c.data
    control = (
        OperationGuards(SystemClock(), CancelSwitch())
        if shared_run is None
        else shared_run.deps.controls
    )
    plans = EvidenceRunPlans(d.store, control)
    run = plans.load(d.plan.run, command())
    runs: RunJournal
    if shared_run is None:
        runroot = root / "actual-task-journal"
        runroot.mkdir()
        runs = FileRunJournal(
            runroot, d.plan.run, control, d.store, capacity=run.run_capacity
        )
        Harness(
            runroot,
            d.store,
            runs,
            d.plan.run,
            d.plan.claim_ref,
            CancelSwitch(),
            run.run_capacity,
        ).running()
    else:
        runs = shared_run.deps.runs
    admission = replace(c.deps, runs=runs, controls=control)
    phases = UnitPhases(c)
    intent = c.request.intent
    scope = c.inputs.candidate.scope
    browser_token = allocation("browser").model_copy(
        update={
            "owner": scope.owner,
            "attempt_id": scope.attempt_id,
            "recovery_ref": c.inputs.candidate_inputs.prepared.recovery_ref,
        }
    )
    reset = ResetPlan(
        scope=scope,
        parent_operation_id="task-original-prepare",
        spec_ref=c.inputs.candidate.spec_ref,
        task_recovery_ref=c.inputs.candidate_inputs.prepared.recovery_ref,
        environment_recovery_ref=c.inputs.source_inputs.reset_inputs.plan.environment_recovery_ref,
        attempt_allocations=(browser_token,),
    )
    reset_ref = put(d.store, reset, "reset-plan/1")
    closure = ClosureReceipt(
        token=browser_token,
        operation_id="task-browser-closed",
        status="closed",
        evidence=(put(d.store, {"unit_terminated": True}),),
    )
    closure_ref = put(d.store, closure, "closure-receipt/1")
    phases.closed = ClosedTaskResources(
        reset_plan=reset,
        reset_plan_ref=reset_ref,
        closures=(closure,),
        closure_refs=(closure_ref,),
    )
    from task_execution_reset_fixtures import candidate_reset

    phases.reset = candidate_reset(
        c.inputs, d.store, reset, reset_ref, closure, closure_ref
    )
    contract = EvaluationContract(
        identity=intent.binding.task,
        attempt_id=intent.binding.attempt_id,
        task_contract_ref=put(d.store, {"unit_native_contract": True}),
        public_task_ref=d.plan.task.public_task_ref,
        completion_spec_ref=put(d.store, {"unit_completion": True}),
        requirements=EvidenceRequirements(),
        scope="engineering",
    )
    op = command(
        "original-task-execution"
        + ("-" + intent.binding.attempt_id if shared_run is not None else ""),
        attempt=intent.binding.attempt_id,
    )
    plan = TaskExecutionPlan(
        intent=intent,
        reset_plan_ref=reset_ref,
        declaration_ref=put(d.store, {"unit_original_preparation": True}),
        skill_ref=c.request.skill_ref,
        evaluation=contract,
        operation=op,
        read_operation=command(
            "task-independent-read"
            + ("-" + intent.binding.attempt_id if shared_run is not None else "")
        ),
        cleanup_seconds=30,
    )
    source = d.journal().read(command())
    skill = source.project().candidates[intent.candidate_slot].response.skill
    params = put(d.store, {"unit_original_parameters": True}, "model-parameters/1")
    memory = run.policies.actor_memory
    assert isinstance(memory, InactivePolicy)
    actor_request = ActorRunRequest(
        scope=scope,
        task=c.inputs.candidate_inputs.public_task,
        skill=skill,
        memory=memory,
        initial_observation_ref=c.inputs.candidate_inputs.observation_ref,
        model_allocation=allocation("actor", attempt=False),
        browser_allocation=browser_token,
        parameters_refs=(params,) * d.plan.max_actor_generations,
        operation=op,
        generation_seconds=10,
        interaction_seconds=10,
        cleanup_seconds=15,
    )
    phases.initialized = InitializedTask(
        baseline_ref=c.inputs.candidate_ref,
        equivalence_ref=c.request.equivalence_ref,
        actor=actor_request,
    )
    traceroot = root / "task-trace"
    traceroot.mkdir()
    traceplan = TracePlan(
        binding=intent.binding,
        scope=scope,
        initial_observation_ref=actor_request.initial_observation_ref,
        max_generations=d.plan.max_actor_generations,
        max_interactions=d.plan.max_interactions,
        capacity=TraceCapacity(
            max_events=128,
            max_bytes=2 * 1024**2,
            max_event_bytes=32768,
            max_trace_bytes=2 * 1024**2,
        ),
    )
    journal = FileTraceJournal(traceroot, traceplan, control, d.store, UnitAuthority())
    journal.create(
        traceplan,
        command(
            "task-trace-created"
            + ("-" + intent.binding.attempt_id if shared_run is not None else ""),
            attempt=intent.binding.attempt_id,
        ),
    )
    model = UnitModel(phases)
    browser = UnitBrowser(phases, journal)
    runner = RecordedActorRunner(
        ActorLoopDeps(
            journal,
            d.store,
            EvidenceObservations(d.store, control),
            model,
            browser,
            RecordedActorDecisions(d.store, control),
            prepare_actor,
            RunAuthority(),
            control,
            SystemClock(),
        )
    )
    actor = UnitActorBinding(runner, phases)
    from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords

    states = EvidenceStateRecords(d.store, control, d.context_authority)
    deps = TaskExecutionDeps(
        d.journal(),
        runs,
        admission,
        phases,
        phases,
        actor,
        phases,
        phases,
        phases,
        states,
        phases,
        d.store,
        control,
        SystemClock(),
    )
    return TaskCase(c, plan, deps, phases, model, browser, actor)
