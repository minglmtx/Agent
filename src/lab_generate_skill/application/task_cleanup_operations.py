"""Cleanup-only provenance; cannot admit prepare, Actor, or another attempt."""

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.execution import AttemptRecord
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan


def require_original_cleanup_operation(
    plan: TaskExecutionPlan,
    declaration: TaskFinalizationPlan,
    preparation: SiteTaskPreparationPlan,
    reset: ResetPlan,
    attempt: AttemptRecord,
    operation: OperationContext,
) -> None:
    if (
        operation.mode != "cleanup"
        or operation.cancellation_ref is not None
        or (operation.run_id, operation.owner_id, operation.attempt_id)
        != (
            declaration.scope.owner.run_id,
            declaration.scope.owner.owner_id,
            declaration.scope.attempt_id,
        )
        or attempt.stage not in ("closing", "restoring")
    ):
        raise OwnershipConflict(
            "Only original acknowledged closing/restoring cleanup is allowed"
        )
    root = attempt.events[-1].operation
    if (
        root.operation_id != plan.operation.operation_id + "." + attempt.stage
        or root.parent_operation_id != plan.operation.operation_id
    ):
        raise OwnershipConflict("Cleanup journal lost original task parent")
    if operation == root:
        return
    if attempt.stage != "restoring" or operation.deadline > root.deadline:
        raise OwnershipConflict(
            "Native recovery requires original restoring stage/deadline"
        )
    expected = {
        declaration.restore_operation_id: (
            reset.parent_operation_id,
            reset.task_recovery_ref,
        ),
        declaration.resume_operation_id: (
            declaration.restore_operation_id,
            reset.environment_recovery_ref,
        ),
        declaration.qualification_operation_id: (
            reset.parent_operation_id,
            reset.environment_recovery_ref,
        ),
        declaration.reset_operation_id: (
            reset.parent_operation_id,
            reset.environment_recovery_ref,
        ),
    }
    original = expected.get(operation.operation_id)
    if (
        original is None
        or (operation.parent_operation_id, operation.recovery_ref) != original
        or operation.allocation_id != preparation.snapshot_operation.allocation_id
    ):
        raise OwnershipConflict(
            "Cleanup changed frozen native phase/allocation/recovery"
        )
