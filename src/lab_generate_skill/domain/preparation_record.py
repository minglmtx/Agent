"""Exact persisted preparation inputs/results; no execution or baseline authority."""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract
from .evidence import EvidenceRef
from .site_task import SiteTaskRequest, SiteTaskResult
from .task import TaskBinding, PublicTask
from .state_checks import InitialStateSpec
from .preparation import EnvironmentBaseline
from .lifecycle import RecoveryPlan
from .state_scope import private_state_ref
from .errors import OwnershipConflict


class PreparationSelection(Contract):
    schema_version: Literal["preparation-selection/1"] = "preparation-selection/1"
    request_ref: EvidenceRef
    result_ref: EvidenceRef
    environment_ref: EvidenceRef

    @model_validator(mode="after")
    def refs(self) -> Self:
        for ref, schema in (
            (self.request_ref, "site-task-request/2"),
            (self.result_ref, "site-task-result/1"),
            (self.environment_ref, "environment-baseline/1"),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json":
                raise ValueError("Preparation requires JSON records")
        return self


class PreparationInputs(Contract):
    selection: PreparationSelection
    request: SiteTaskRequest
    result: SiteTaskResult
    binding: TaskBinding
    public_task: PublicTask
    spec: InitialStateSpec
    environment: EnvironmentBaseline
    recovery: RecoveryPlan

    @model_validator(mode="after")
    def original(self) -> Self:
        r, e = self.request, self.environment
        scope = e.scope
        if r.action != "prepare" or self.result.request_sha256 != r.digest:
            raise OwnershipConflict(
                "Preparation result must bind original prepare request"
            )
        if (
            r.task,
            self.binding.identity,
            self.public_task.identity,
            self.spec.task,
        ) != (scope.task,) * 4:
            raise OwnershipConflict("Preparation task differs from environment/binding")
        if (
            r.operation.run_id,
            r.operation.owner_id,
            r.operation.attempt_id,
            r.operation.allocation_id,
        ) != (
            scope.owner.run_id,
            scope.owner.owner_id,
            scope.attempt_id,
            e.allocation.allocation_id,
        ):
            raise OwnershipConflict(
                "Preparation changed original environment ownership"
            )
        if (
            e.spec_ref != self.binding.baseline_ref
            or e.checks.required != self.spec.environment_checks
        ):
            raise OwnershipConflict("Preparation changed declared environment coverage")
        if r.operation.operation_id == e.operation.operation_id:
            raise OwnershipConflict(
                "Environment and preparation need distinct operations"
            )
        if (
            self.recovery.owner,
            self.recovery.attempt_id,
            self.recovery.state_coverage,
        ) != (scope.owner, scope.attempt_id, self.spec.task_reset_checks):
            raise OwnershipConflict(
                "Preparation recovery differs from original scope/coverage"
            )
        return self


class PreparedPublication(Contract):
    schema_version: Literal["prepared-publication/1"] = "prepared-publication/1"
    selection: PreparationSelection
    preparation_ref: EvidenceRef
    prepared_ref: EvidenceRef

    @model_validator(mode="after")
    def refs(self) -> Self:
        private_state_ref(self.preparation_ref, "preparation-receipt/1")
        private_state_ref(self.prepared_ref, "prepared-task/1")
        return self


class PreparationRecordFailure(RuntimeError):
    """Keep the primary error and returned candidates; never rerun site actions."""

    def __init__(
        self, phase: str, primary: BaseException, references: tuple[EvidenceRef, ...]
    ) -> None:
        self.phase, self.primary, self.references = phase, primary, references
        super().__init__(
            "Preparation record failed at " + phase + "; reconcile original facts"
        )
