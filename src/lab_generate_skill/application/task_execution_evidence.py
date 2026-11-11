"""Read the original complete task graph, sealed stages and original closure.

Shared by construction completion and allowed Teacher material; no role call,
new permission, resource effect, ledger, retry or historical result upgrade.
"""

from dataclasses import dataclass
from lab_generate_skill.domain.actor_run import ActorRunRequest, ActorStop
from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.evaluation import Evaluation
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.reset import ResetPlan, ResetReceipt
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    TaskCaptureResult,
    ClosedTaskResources,
)
from lab_generate_skill.domain.task_execution_result import (
    TaskAttemptResult,
    ExecutedTaskReceipt,
)
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.state_records import StateRecords
from lab_generate_skill.ports.task_execution import TaskClosureAuthority
from .teacher_actor_reads import canonical


from lab_generate_skill.domain.construction import ConstructionAttemptResult
from lab_generate_skill.domain.execution_task_result import ExecutionTaskResult


@dataclass(frozen=True)
class TaskExecutionEvidenceDeps:
    evidence: EvidenceReader
    runs: RunJournal
    states: StateRecords
    closure: TaskClosureAuthority

    def __post_init__(self) -> None:
        if any(
            v is None for v in (self.evidence, self.runs, self.states, self.closure)
        ):
            raise ValueError(
                "Original result, journal, state and closure authorities required"
            )


@dataclass(frozen=True)
class OriginalTaskExecutionEvidence:
    envelope: TaskAttemptResult
    executed: ExecutedTaskReceipt
    plan: TaskExecutionPlan
    actor: ActorRunRequest
    trace: InteractionTrace
    stop: ActorStop
    closed: ClosedTaskResources


def read_original_task_execution(
    result: ConstructionAttemptResult | ExecutionTaskResult,
    deps: TaskExecutionEvidenceDeps,
    operation: OperationContext,
    *,
    control: OperationControl,
) -> OriginalTaskExecutionEvidence:
    result = (
        ExecutionTaskResult.model_validate(result)
        if isinstance(result, ExecutionTaskResult)
        else ConstructionAttemptResult.model_validate(result)
    )
    single = isinstance(result, ExecutionTaskResult)
    op = OperationContext.model_validate(operation)
    owner = result.intent.binding.run.owner
    if (op.run_id, op.owner_id, op.attempt_id, op.allocation_id, op.recovery_ref) != (
        owner.run_id,
        owner.owner_id,
        None,
        None,
        None,
    ):
        raise OwnershipConflict(
            "Original task evidence requires original run-level read scope"
        )
    control.checkpoint()
    evidence = deps.evidence
    envelope = canonical(
        result.attempt_ref,
        "execution-attempt-result/1" if single else "attempt-result/1",
        TaskAttemptResult,
        evidence,
        control,
    )
    executed = canonical(
        envelope.execution_ref,
        "executed-task-receipt/2" if single else "executed-task-receipt/1",
        ExecutedTaskReceipt,
        evidence,
        control,
    )
    plan = canonical(
        executed.plan_ref,
        "task-execution-plan/2" if single else "task-execution-plan/1",
        TaskExecutionPlan,
        evidence,
        control,
    )
    if not (
        result.intent == envelope.intent == executed.intent == plan.intent
        and result.generations == envelope.generations == executed.generations
        and result.interactions == envelope.interactions == executed.interactions
        and result.evaluation_ref == executed.evaluation_ref
    ):
        raise EvidenceIntegrityError(
            "Task/Teacher changed original result lineage/counters"
        )
    request = canonical(
        executed.actor_request_ref,
        executed.actor_request_ref.content_schema,
        ActorRunRequest,
        evidence,
        control,
    )
    trace = canonical(
        executed.trace_ref, "interaction-trace/1", InteractionTrace, evidence, control
    )
    stop = canonical(
        trace.stop_evidence_ref, "trace-stop/1", ActorStop, evidence, control
    )
    native_request = canonical(
        stop.request_ref,
        stop.request_ref.content_schema,
        ActorRunRequest,
        evidence,
        control,
    )
    # The task handoff and runner independently publish the same canonical
    # request under their original producers. Preserve both full references;
    # the native Teacher part must use the runner's actual stop-bound reference.
    if native_request != request:
        raise EvidenceIntegrityError(
            "Original native Actor request differs from task handoff bytes"
        )
    evaluation = canonical(
        executed.evaluation_ref,
        "evaluation/1",
        Evaluation,
        evidence,
        control,
        2 * 1024**2,
    )
    captured = canonical(
        executed.capture_ref,
        "task-capture-result/1",
        TaskCaptureResult,
        evidence,
        control,
    )
    closed = canonical(
        executed.closed_ref,
        "closed-task-resources/1",
        ClosedTaskResources,
        evidence,
        control,
    )
    reset_plan = canonical(
        plan.reset_plan_ref, "reset-plan/1", ResetPlan, evidence, control, 2 * 1024**2
    )
    if closed.reset_plan != reset_plan:
        raise EvidenceIntegrityError("Closure changed original complete Reset plan")
    for ref, closure in zip(closed.closure_refs, closed.closures, strict=True):
        if (
            canonical(
                ref, "closure-receipt/1", ClosureReceipt, evidence, control, 2 * 1024**2
            )
            != closure
        ):
            raise EvidenceIntegrityError(
                "Closure summary differs from original complete bytes"
            )
    scope = request.scope
    if (
        (scope.owner, scope.task, scope.attempt_id)
        != (
            result.intent.binding.run.owner,
            result.intent.binding.task,
            result.intent.binding.attempt_id,
        )
        or request.operation != plan.operation
        or request.skill.content_digest != result.intent.skill_digest
        or trace.scope != scope
        or trace.initial_observation_ref != request.initial_observation_ref
        or (trace.generations, trace.interactions)
        != (result.generations, result.interactions)
        or evaluation != result.evaluation
        or captured.contract != plan.evaluation
        or evaluation.contract_ref != plan.evaluation.task_contract_ref
        or closed.reset_plan.scope != scope
        or closed.reset_plan_ref != plan.reset_plan_ref
    ):
        raise OwnershipConflict(
            "Task/Teacher lost original Actor/judgment/reset association"
        )
    before = RunSnapshot.model_validate(deps.runs.read(op))
    attempts = before.project()[1]
    record = next((a for a in attempts if a.binding == result.intent.binding), None)
    if (
        before.binding != result.intent.binding.run
        or record is None
        or record.stage != "sealed"
    ):
        raise OwnershipConflict("Task/Teacher requires original sealed task history")
    expected = {
        "planned": (executed.plan_ref,),
        "baseline_verified": (executed.baseline_ref, executed.equivalence_ref),
        "executing": (executed.actor_request_ref,),
        "captured": (executed.trace_ref, executed.capture_ref),
        "evaluated": (executed.evaluation_ref,),
        "restoring": (executed.closed_ref,),
        "sealed": (executed.reset_ref,),
    }
    for stage, refs in expected.items():
        events = [e for e in record.events if e.stage == stage]
        if len(events) != 1 or any(r not in events[0].outputs for r in refs):
            raise EvidenceIntegrityError(
                "Task/Teacher result is not in original stage history: " + stage
            )
    if any(
        e.primary_error is not None or e.cleanup_errors or e.stop_reason is not None
        for e in record.events
    ):
        raise EvidenceIntegrityError(
            "Diagnostic seal is not confirmed original task completion"
        )
    baseline = deps.states.load_baseline(executed.baseline_ref, op)
    reset = deps.states.load_reset(executed.reset_ref, op)
    if (
        baseline
        != canonical(
            executed.baseline_ref,
            "baseline-receipt/1",
            BaselineReceipt,
            evidence,
            control,
        )
        or reset
        != canonical(
            executed.reset_ref, "reset-receipt/1", ResetReceipt, evidence, control
        )
        or baseline.scope != scope
        or baseline.status != "ready"
        or baseline.observation_ref != request.initial_observation_ref
        or reset.scope != scope
        or reset.status != "safe"
        or reset.plan_ref != plan.reset_plan_ref
        or reset.closure_refs != closed.closure_refs
    ):
        raise EvidenceIntegrityError(
            "Task/Teacher requires original ready baseline and complete safe Reset"
        )
    deps.closure.verify_closed(plan, closed, op, control)
    control.checkpoint()
    if deps.runs.read(op) != before:
        raise OwnershipConflict(
            "Original run history changed during task material admission"
        )
    return OriginalTaskExecutionEvidence(
        envelope, executed, plan, request, trace, stop, closed
    )
