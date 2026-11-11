"""One Actor/capture/judgment implementation for full and initialized task entries."""

from dataclasses import dataclass
from lab_generate_skill.domain.task_admission import TaskAdmissionState
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    InitializedTask,
    TaskCaptureResult,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.evaluation import Evaluation
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.task_execution_deps import TaskExecutionDeps
from .execution_stage import execution_stage
from .task_execution_events import TaskExecutionEvents
from .actor_loop import ActorLoopFailure


@dataclass
class TaskTailState:
    # Acknowledged executing append, not a permission or cached live gate.
    entered: bool = False
    trace: TraceSnapshot | None = None
    evaluation: Evaluation | None = None


def verify_task_current(
    plan: TaskExecutionPlan,
    deps: TaskExecutionDeps,
    snapshot: RunSnapshot,
    state: TaskAdmissionState,
    operation: OperationContext,
) -> None:
    deps.source.verify_current(plan, state, snapshot, operation)


def execute_task_tail(
    plan: TaskExecutionPlan,
    deps: TaskExecutionDeps,
    state: TaskAdmissionState,
    initialized: InitializedTask,
    events: TaskExecutionEvents,
    result: TaskTailState,
) -> None:
    control = deps.controls.bind(plan.operation)
    try:
        with execution_stage(deps.controls, "actor", plan.operation):
            admitted = deps.source.initialize(
                plan, state, initialized, events.snapshot, control
            )
            admitted_ref = events.put("admission", admitted, plan.operation)
            actor_ref = events.put("actor_request", initialized.actor, plan.operation)
            events.append("executing", plan.operation, (admitted_ref, actor_ref))
            result.entered = True
            verify_task_current(plan, deps, events.snapshot, state, plan.operation)
            runner = deps.actors.bind(initialized, admitted)
            result.trace = TraceSnapshot.model_validate(runner.run(initialized.actor))
            view = result.trace.project()
            if (
                result.trace.plan.binding != plan.intent.binding
                or result.trace.plan.scope != initialized.actor.scope
                or result.trace.plan.initial_observation_ref
                != initialized.actor.initial_observation_ref
                or result.trace.plan.max_generations > state.max_generations
                or result.trace.plan.max_interactions > state.max_interactions
                or view.sealed is None
            ):
                raise OwnershipConflict(
                    "Actor returned another or unsealed original task trace"
                )
            trace_ref = events.put("trace", view.sealed, plan.operation)
            events.put("trace_snapshot", result.trace, plan.operation)
        with execution_stage(deps.controls, "capture", plan.operation):
            op = events.operation("capture")
            verify_task_current(plan, deps, events.snapshot, state, op)
            captured = TaskCaptureResult.model_validate(
                deps.capture.capture(plan, result.trace, op, deps.controls.bind(op))
            )
            if captured.contract != plan.evaluation:
                raise OwnershipConflict("Capture changed original evaluation contract")
            capture_ref = events.put("capture", captured, op)
            events.append("captured", op, (trace_ref, capture_ref))
        with execution_stage(deps.controls, "judgment", plan.operation):
            op = events.operation("evaluate")
            verify_task_current(plan, deps, events.snapshot, state, op)
            result.evaluation = Evaluation.model_validate(
                deps.evaluator.evaluate(
                    plan.evaluation, deps.evidence, deps.controls.bind(op)
                )
            )
            if (
                result.evaluation.identity,
                result.evaluation.attempt_id,
                result.evaluation.contract_ref,
            ) != (
                plan.evaluation.identity,
                plan.evaluation.attempt_id,
                plan.evaluation.task_contract_ref,
            ):
                raise OwnershipConflict(
                    "Evaluator returned another original task/attempt/contract"
                )
            evaluation_ref = events.put("evaluation", result.evaluation, op)
            events.append("evaluated", op, (evaluation_ref,))
    except ActorLoopFailure as error:
        result.trace = error.snapshot
        raise
