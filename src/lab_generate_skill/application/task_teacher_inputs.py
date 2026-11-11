"""Allowed Teacher view of the original complete task, using the shared reader."""

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_teacher import TaskTeacherInput
from lab_generate_skill.domain.teacher_attempt import TeacherAttemptInput
from lab_generate_skill.ports.lifecycle import OperationControl
from .task_execution_evidence import (
    TaskExecutionEvidenceDeps as TaskTeacherReadDeps,
    read_original_task_execution,
)

__all__ = ["TaskTeacherReadDeps", "task_teacher_input"]


def task_teacher_input(
    original: TaskTeacherInput,
    deps: TaskTeacherReadDeps,
    operation: OperationContext,
    *,
    control: OperationControl,
) -> TeacherAttemptInput:
    original = TaskTeacherInput.model_validate(original)
    op = OperationContext.model_validate(operation)
    parent = original.operation
    if op != parent and not (
        op.mode == "cleanup"
        and op.parent_operation_id == parent.operation_id
        and (op.run_id, op.owner_id, op.attempt_id, op.allocation_id, op.recovery_ref)
        == (parent.run_id, parent.owner_id, None, None, None)
    ):
        raise OwnershipConflict(
            "Task/Teacher read requires original command or parent cleanup"
        )
    control.checkpoint()
    actual = read_original_task_execution(original.result, deps, op, control=control)
    scope = actual.actor.scope
    if (scope.owner, scope.task, scope.context_id, scope.attempt_id) != (
        original.scope.owner,
        original.scope.task,
        original.scope.context_id,
        original.result.intent.binding.attempt_id,
    ):
        raise OwnershipConflict(
            "Task/Teacher lost original Actor/judgment/reset association"
        )
    return TeacherAttemptInput(
        scope=original.scope,
        candidate_slot=original.result.intent.candidate_slot,
        actor_request_ref=actual.stop.request_ref,
        trace_ref=actual.executed.trace_ref,
        evaluation_ref=actual.executed.evaluation_ref,
        feedback=original.feedback,
        operation=original.operation,
    )
