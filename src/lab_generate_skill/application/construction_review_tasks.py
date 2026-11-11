"""Original full task/native/Reset proof and independent same-release judgment."""

from lab_generate_skill.domain.review import ReviewTask, ReviewFinding
from lab_generate_skill.domain.construction import (
    ConstructionAttemptResult,
    ConstructionPlan,
)
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    TaskCaptureResult,
)
from lab_generate_skill.domain.task_execution_result import (
    TaskAttemptResult,
    ExecutedTaskReceipt,
)
from lab_generate_skill.domain.evaluation import Evaluation, EvaluationContract
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.evaluator import Evaluator
from lab_generate_skill.ports.lifecycle import OperationControl
from .task_teacher_review import TaskTeacherReviewDeps, review_task_teacher_attempt
from .teacher_actor_reads import canonical
from .context_evidence import read_bytes
from .construction_actor_configuration import verify_construction_actor_configuration
from lab_generate_skill.domain.actor_run import ActorRunRequest


def review_construction_task(
    item: ReviewTask,
    result: ConstructionAttemptResult,
    construction: ConstructionPlan,
    deps: TaskTeacherReviewDeps,
    contexts: ContextRecords,
    evaluator: Evaluator,
    control: OperationControl,
) -> tuple[ReviewFinding, TaskExecutionPlan]:
    receipt = review_task_teacher_attempt(
        item.published, deps, item.operation, control=control
    )
    if (
        receipt.original.result != result
        or result.intent.public_context_ref != construction.public_context_ref
    ):
        raise EvidenceIntegrityError(
            "Review task descriptor changed original construction result"
        )
    evidence = deps.original.evidence
    envelope = canonical(
        result.attempt_ref, "attempt-result/1", TaskAttemptResult, evidence, control
    )
    executed = canonical(
        envelope.execution_ref,
        "executed-task-receipt/1",
        ExecutedTaskReceipt,
        evidence,
        control,
    )
    plan = canonical(
        executed.plan_ref, "task-execution-plan/1", TaskExecutionPlan, evidence, control
    )
    if construction.actor_context_configuration_ref is not None:
        actual_actor = canonical(
            executed.actor_request_ref,
            "actor-run-request/2",
            ActorRunRequest,
            evidence,
            control,
        )
        verify_construction_actor_configuration(
            construction, actual_actor, evidence, control
        )
    captured = canonical(
        executed.capture_ref,
        "task-capture-result/1",
        TaskCaptureResult,
        evidence,
        control,
    )
    equivalent = contexts.load_equivalence(executed.equivalence_ref, item.operation)
    scope = receipt.original.scope
    if (
        equivalent.status != "equivalent"
        or equivalent.source_context_receipt_ref != construction.context_receipt_ref
        or equivalent.candidate_baseline_ref != executed.baseline_ref
        or (
            equivalent.scope.owner,
            equivalent.scope.task,
            equivalent.scope.context_id,
            equivalent.scope.attempt_id,
        )
        != (scope.owner, scope.task, scope.context_id, result.intent.binding.attempt_id)
        or plan.intent.binding.run != construction.run
        or plan.intent.binding.claim_ref != construction.claim_ref
        or plan.intent.binding.task != construction.task.identity
        or captured.contract != plan.evaluation
    ):
        raise EvidenceIntegrityError(
            "Review lost measured source/candidate or original plan association"
        )
    requirements = evaluator.requirements(plan.evaluation)
    if requirements != captured.contract.requirements:
        raise EvidenceIntegrityError(
            "Review evaluator changed original capture requirements"
        )
    for ref in captured.references:
        # No new site/database query. Every declared captured object must exist.
        read_bytes(evidence, ref, 64 * 1024**2, control)
    reproduced = Evaluation.model_validate(
        evaluator.evaluate(plan.evaluation, evidence, control)
    )
    if (
        reproduced.identity,
        reproduced.attempt_id,
        reproduced.contract_ref,
        reproduced.evaluator_id,
        reproduced.evaluator_version,
        reproduced.supersedes,
    ) != (
        result.evaluation.identity,
        result.evaluation.attempt_id,
        result.evaluation.contract_ref,
        result.evaluation.evaluator_id,
        result.evaluation.evaluator_version,
        result.evaluation.supersedes,
    ):
        raise EvidenceIntegrityError(
            "Same-release review cannot change evaluator identity or evaluation branch"
        )
    control.checkpoint()
    return (
        ReviewFinding(
            attempt_id=result.intent.binding.attempt_id,
            candidate_slot=result.intent.candidate_slot,
            original_evaluation_ref=result.evaluation_ref,
            execution_ref=envelope.execution_ref,
            reset_ref=executed.reset_ref,
            reproduced=reproduced,
            matches_recorded=reproduced == result.evaluation,
        ),
        plan,
    )
