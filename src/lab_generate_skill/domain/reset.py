"""Normal attempt reset facts, separate from crashed-writer recovery.

Plan exists before prepare and can be consumed even when no PreparedTask or
BaselineReceipt was returned. Safe reset is not batch closure or training entry.
"""

from typing import ClassVar, Literal, Self
from pydantic import Field, model_validator
from .errors import OwnershipConflict
from .evidence import EvidenceRef
from .lifecycle import AllocationToken, ClosureReceipt, OperationContext, RecoveryPlan
from .state_checks import InitialStateSpec, StateChecks
from .state_scope import StateScope, StateFact, private_state_ref
from .validation import Contract, Identifier


class ResetPlan(Contract):
    schema_version: Literal["reset-plan/1"] = "reset-plan/1"
    scope: StateScope
    parent_operation_id: Identifier
    spec_ref: EvidenceRef
    task_recovery_ref: EvidenceRef
    environment_recovery_ref: EvidenceRef
    attempt_allocations: tuple[AllocationToken, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def original_resources(self) -> Self:
        private_state_ref(self.spec_ref, "initial-state-spec/1")
        private_state_ref(self.task_recovery_ref, "recovery-plan/1")
        private_state_ref(self.environment_recovery_ref, "recovery-plan/1")
        tokens = self.attempt_allocations
        if len({t.allocation_id for t in tokens}) != len(tokens):
            raise ValueError("Reset cannot duplicate allocations")
        if len({(t.provider_id, t.expected_resource_id) for t in tokens}) != len(
            tokens
        ):
            raise ValueError("Reset cannot alias one resource as different allocations")
        if any(
            t.owner != self.scope.owner
            or t.scope != "attempt"
            or t.attempt_id != self.scope.attempt_id
            for t in tokens
        ):
            raise ValueError(
                "Attempt reset cannot close a different owner/attempt or batch resource"
            )
        return self


class ResetFact(StateFact):
    operation_mode: ClassVar[Literal["execute", "cleanup"]] = "cleanup"
    checks: StateChecks


class TaskResetReceipt(ResetFact):
    schema_version: Literal["task-reset/1"] = "task-reset/1"
    recovery_ref: EvidenceRef
    after_closure_refs: tuple[EvidenceRef, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def dependencies(self) -> Self:
        private_state_ref(self.recovery_ref, "recovery-plan/1")
        for ref in self.after_closure_refs:
            private_state_ref(ref, "closure-receipt/1")
        if len(set(self.after_closure_refs)) != len(self.after_closure_refs):
            raise ValueError("Duplicate closure reference")
        if self.operation.recovery_ref != self.recovery_ref:
            raise ValueError("Task reset operation must retain original recovery")
        return self


class EnvironmentResetReceipt(ResetFact):
    schema_version: Literal["environment-reset/1"] = "environment-reset/1"
    recovery_ref: EvidenceRef
    after_task_reset_ref: EvidenceRef

    @model_validator(mode="after")
    def dependencies(self) -> Self:
        private_state_ref(self.recovery_ref, "recovery-plan/1")
        private_state_ref(self.after_task_reset_ref, "task-reset/1")
        if self.operation.recovery_ref != self.recovery_ref:
            raise ValueError("Environment reset must retain original recovery")
        return self


class ResetHealthReceipt(ResetFact):
    schema_version: Literal["reset-health/1"] = "reset-health/1"
    after_environment_reset_ref: EvidenceRef

    @model_validator(mode="after")
    def dependency(self) -> Self:
        private_state_ref(self.after_environment_reset_ref, "environment-reset/1")
        return self


class ResetReceipt(StateFact):
    operation_mode: ClassVar[Literal["execute", "cleanup"]] = "cleanup"
    schema_version: Literal["reset-receipt/1"] = "reset-receipt/1"
    plan_ref: EvidenceRef
    closure_refs: tuple[EvidenceRef, ...] = Field(min_length=1)
    task_reset_ref: EvidenceRef
    environment_reset_ref: EvidenceRef
    health_ref: EvidenceRef
    status: Literal["safe", "quarantined"]

    @model_validator(mode="after")
    def references(self) -> Self:
        for ref, schema in (
            (self.plan_ref, "reset-plan/1"),
            (self.task_reset_ref, "task-reset/1"),
            (self.environment_reset_ref, "environment-reset/1"),
            (self.health_ref, "reset-health/1"),
        ):
            private_state_ref(ref, schema)
        for ref in self.closure_refs:
            private_state_ref(ref, "closure-receipt/1")
        if len(set(self.closure_refs)) != len(self.closure_refs):
            raise ValueError("Reset cannot duplicate closure evidence")
        return self


class ResetInputs(Contract):
    plan: ResetPlan
    plan_ref: EvidenceRef
    spec: InitialStateSpec
    task_recovery: RecoveryPlan
    environment_recovery: RecoveryPlan
    closures: tuple[ClosureReceipt, ...]
    closure_refs: tuple[EvidenceRef, ...]
    task: TaskResetReceipt
    task_ref: EvidenceRef
    environment: EnvironmentResetReceipt
    environment_ref: EvidenceRef
    health: ResetHealthReceipt
    health_ref: EvidenceRef


def assemble_reset(inputs: ResetInputs, operation: OperationContext) -> ResetReceipt:
    inputs = ResetInputs.model_validate(inputs)
    operation = OperationContext.model_validate(operation)
    plan = inputs.plan
    if (
        len(
            {
                op.operation_id
                for op in (
                    inputs.task.operation,
                    inputs.environment.operation,
                    inputs.health.operation,
                    operation,
                )
            }
        )
        != 4
    ):
        raise OwnershipConflict("Reset stages require distinct operation identities")
    if inputs.spec.task != plan.scope.task or any(
        f.scope != plan.scope for f in (inputs.task, inputs.environment, inputs.health)
    ):
        raise OwnershipConflict(
            "Reset cannot combine different task/owner/attempt/context"
        )
    if any(
        op.parent_operation_id != plan.parent_operation_id
        for op in (
            operation,
            inputs.task.operation,
            inputs.environment.operation,
            inputs.health.operation,
        )
    ):
        raise OwnershipConflict(
            "Reset cleanup must refer to the declared original execution"
        )
    if tuple(c.token for c in inputs.closures) != plan.attempt_allocations or len(
        inputs.closure_refs
    ) != len(inputs.closures):
        raise OwnershipConflict(
            "Reset requires all exact original attempt closures in plan order"
        )
    if (
        inputs.task.recovery_ref,
        inputs.environment.recovery_ref,
        inputs.task.after_closure_refs,
        inputs.environment.after_task_reset_ref,
        inputs.health.after_environment_reset_ref,
    ) != (
        plan.task_recovery_ref,
        plan.environment_recovery_ref,
        inputs.closure_refs,
        inputs.task_ref,
        inputs.environment_ref,
    ):
        raise OwnershipConflict(
            "Reset dependencies must retain close -> task -> environment -> health"
        )
    for recovery, attempt, required in (
        (inputs.task_recovery, plan.scope.attempt_id, inputs.spec.task_reset_checks),
        (inputs.environment_recovery, None, inputs.spec.environment_reset_checks),
    ):
        if (
            recovery.owner != plan.scope.owner
            or recovery.attempt_id != attempt
            or recovery.state_coverage != required
        ):
            raise OwnershipConflict(
                "Reset must preserve entire declared recovery coverage and owner"
            )
    for facts, required in (
        (inputs.task.checks, inputs.spec.task_reset_checks),
        (inputs.environment.checks, inputs.spec.environment_reset_checks),
        (inputs.health.checks, inputs.spec.health_checks),
    ):
        if facts.required != required:
            raise OwnershipConflict("Reset cannot reduce required checks")
    safe = all(c.status == "closed" for c in inputs.closures) and all(
        f.checks.status == "pass"
        for f in (inputs.task, inputs.environment, inputs.health)
    )
    return ResetReceipt(
        scope=plan.scope,
        operation=operation,
        plan_ref=inputs.plan_ref,
        closure_refs=inputs.closure_refs,
        task_reset_ref=inputs.task_ref,
        environment_reset_ref=inputs.environment_ref,
        health_ref=inputs.health_ref,
        status="safe" if safe else "quarantined",
    )
