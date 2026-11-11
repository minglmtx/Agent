"""Environment/preparation facts and prepared task, never model prompt data."""

from typing import Literal, Self
from pydantic import model_validator
from .evidence import EvidenceRef
from .lifecycle import AllocationToken
from .state_checks import StateChecks
from .state_scope import StateScope, StateFact, private_state_ref
from .task import PublicTask
from .validation import Contract, Sha256


class EnvironmentBaseline(StateFact):
    schema_version: Literal["environment-baseline/1"] = "environment-baseline/1"
    allocation: AllocationToken
    spec_ref: EvidenceRef
    checks: StateChecks
    measured_state_sha256: Sha256

    @model_validator(mode="after")
    def binding(self) -> Self:
        private_state_ref(self.spec_ref, "initial-state-spec/1")
        if self.allocation.owner != self.scope.owner or (
            self.allocation.scope == "attempt"
            and self.allocation.attempt_id != self.scope.attempt_id
        ):
            raise ValueError("Environment baseline must use original owned allocation")
        if self.allocation.scope != "batch":
            raise ValueError(
                "Environment baseline belongs to the batch site lease; attempt resources close separately"
            )
        if self.operation.allocation_id != self.allocation.allocation_id:
            raise ValueError("Environment operation must identify its allocation")
        return self


class PreparationReceipt(StateFact):
    schema_version: Literal["preparation-receipt/1"] = "preparation-receipt/1"
    task_binding_ref: EvidenceRef
    spec_ref: EvidenceRef
    environment_ref: EvidenceRef
    recovery_ref: EvidenceRef
    checks: StateChecks

    @model_validator(mode="after")
    def references(self) -> Self:
        for ref, schema in (
            (self.task_binding_ref, "task-binding/1"),
            (self.spec_ref, "initial-state-spec/1"),
            (self.environment_ref, "environment-baseline/1"),
            (self.recovery_ref, "recovery-plan/1"),
        ):
            private_state_ref(ref, schema)
        if self.operation.recovery_ref != self.recovery_ref:
            raise ValueError("Preparation must identify its predeclared recovery")
        return self


class PreparedTask(Contract):
    schema_version: Literal["prepared-task/1"] = "prepared-task/1"
    scope: StateScope
    public_task: PublicTask
    task_binding_ref: EvidenceRef
    spec_ref: EvidenceRef
    preparation_ref: EvidenceRef
    private_checks_ref: EvidenceRef
    recovery_ref: EvidenceRef

    @model_validator(mode="after")
    def separate_views(self) -> Self:
        if self.public_task.identity != self.scope.task:
            raise ValueError("Prepared public task differs from execution identity")
        for ref, schema in (
            (self.task_binding_ref, "task-binding/1"),
            (self.spec_ref, "initial-state-spec/1"),
            (self.preparation_ref, "preparation-receipt/1"),
            (self.recovery_ref, "recovery-plan/1"),
        ):
            private_state_ref(ref, schema)
        if self.private_checks_ref.visibility != "private":
            raise ValueError("Initial checks specification remains private")
        return self
