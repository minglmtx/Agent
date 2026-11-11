"""One shared typed synthetic reset graph; no native recovery authority."""

from lab_generate_skill.domain.initial_equivalence import EquivalenceInputs
from lab_generate_skill.domain.reset import (
    ResetPlan,
    ResetInputs,
    ResetReceipt,
    TaskResetReceipt,
    EnvironmentResetReceipt,
    ResetHealthReceipt,
    assemble_reset,
)
from lab_generate_skill.domain.lifecycle import (
    ClosureReceipt,
    OperationContext,
    RecoveryPlan,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from evidence_control_fixtures import EvidenceFixtureStore
from construction_storage_fixtures import put
from test_run_journal import command


def candidate_reset(
    inputs: EquivalenceInputs,
    store: EvidenceFixtureStore,
    reset: ResetPlan,
    reset_ref: EvidenceRef,
    closure: ClosureReceipt,
    closure_ref: EvidenceRef,
) -> ResetReceipt:
    scope = inputs.candidate.scope
    old = inputs.source_inputs.reset_inputs

    def cleanup_operation(original: OperationContext) -> OperationContext:
        return original.model_copy(
            update={
                "attempt_id": scope.attempt_id,
                "parent_operation_id": reset.parent_operation_id,
            }
        )

    task_reset = TaskResetReceipt.model_validate(
        old.task.model_copy(
            update={
                "scope": scope,
                "operation": cleanup_operation(old.task.operation).model_copy(
                    update={"recovery_ref": reset.task_recovery_ref}
                ),
                "recovery_ref": reset.task_recovery_ref,
                "after_closure_refs": (closure_ref,),
            }
        )
    )
    task_ref = put(store, task_reset, "task-reset/1")
    env_reset = EnvironmentResetReceipt.model_validate(
        old.environment.model_copy(
            update={
                "scope": scope,
                "operation": cleanup_operation(old.environment.operation),
                "after_task_reset_ref": task_ref,
            }
        )
    )
    env_ref = put(store, env_reset, "environment-reset/1")
    health = ResetHealthReceipt.model_validate(
        old.health.model_copy(
            update={
                "scope": scope,
                "operation": cleanup_operation(old.health.operation),
                "after_environment_reset_ref": env_ref,
            }
        )
    )
    health_ref = put(store, health, "reset-health/1")
    reset_inputs = ResetInputs(
        plan=reset,
        plan_ref=reset_ref,
        spec=inputs.candidate_inputs.spec,
        task_recovery=RecoveryPlan.model_validate_json(
            store.read(reset.task_recovery_ref)
        ),
        environment_recovery=old.environment_recovery,
        closures=(closure,),
        closure_refs=(closure_ref,),
        task=task_reset,
        task_ref=task_ref,
        environment=env_reset,
        environment_ref=env_ref,
        health=health,
        health_ref=health_ref,
    )
    reset_op = command(
        "task-original-reset",
        attempt=scope.attempt_id,
        cleanup_parent=reset.parent_operation_id,
    )
    receipt = assemble_reset(reset_inputs, reset_op)
    return receipt
