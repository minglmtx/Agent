"""Pure original preparation binding; no source admission or resource effects."""

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.task_site_acquisition import SiteTaskAcquired


def require_declared_preparation(
    plan: TaskExecutionPlan,
    declaration: SiteTaskPreparationPlan,
    reset: ResetPlan,
    spec: SiteResourceSpec,
    binding: TaskBinding,
) -> None:
    intent, scope = plan.intent.binding, declaration.scope
    if (scope.owner, scope.task, scope.attempt_id) != (
        intent.run.owner,
        intent.task,
        intent.attempt_id,
    ) or reset.scope != scope:
        raise OwnershipConflict("Preparation changed exact pending attempt/reset scope")
    if (spec.token.owner, spec.token.scope, spec.token.attempt_id) != (
        scope.owner,
        "batch",
        None,
    ):
        raise OwnershipConflict("Original explicitly held batch site required")
    if binding.identity != scope.task:
        raise OwnershipConflict("Preparation changed held instance/task binding")
    if (binding.public_task_ref, binding.baseline_ref) != (
        plan.evaluation.public_task_ref,
        reset.spec_ref,
    ) or declaration.task_binding_ref != plan.evaluation.task_contract_ref:
        raise OwnershipConflict(
            "Preparation changed original public/private task/baseline"
        )
    # The immutable TaskBinding above fixes the original private specification.
    # Native input can be its canonical execution envelope. The mandatory
    # SiteTaskInputChecks proves that exact relation before native dispatch;
    # comparing these two different references rejects legitimate Admin input.
    if (
        declaration.prepare_operation.operation_id,
        declaration.prepare_operation.recovery_ref,
        declaration.environment_operation.recovery_ref,
    ) != (
        reset.parent_operation_id,
        reset.task_recovery_ref,
        reset.environment_recovery_ref,
    ) or reset.environment_recovery_ref != spec.token.recovery_ref:
        raise OwnershipConflict("Preparation changed original reset/recovery lineage")
    operations = (
        declaration.snapshot_operation,
        declaration.prepare_operation,
        declaration.environment_operation,
    )
    if any(
        op.allocation_id != spec.token.allocation_id
        or op.deadline > plan.operation.deadline
        or op.cancellation_ref != plan.operation.cancellation_ref
        for op in operations
    ):
        raise OwnershipConflict(
            "Preparation phases changed original allocation/deadline/cancellation"
        )
    spec.check_operation(declaration.resource_read_operation, "cleanup")


def require_original_preparation(
    plan: TaskExecutionPlan,
    declaration: SiteTaskPreparationPlan,
    reset: ResetPlan,
    spec: SiteResourceSpec,
    started: SiteResourceStarted,
    binding: TaskBinding,
    acquired: SiteTaskAcquired,
) -> None:
    require_declared_preparation(plan, declaration, reset, spec, binding)
    if (
        acquired.scope != declaration.scope
        or acquired.declaration_ref != plan.declaration_ref
        or acquired.operation
        != plan.operation.model_copy(
            update={"operation_id": plan.operation.operation_id + ".acquiring"}
        )
        or started.instance.files != spec.configuration.files
    ):
        raise OwnershipConflict(
            "Acquired binding changed original declaration/phase/site"
        )
