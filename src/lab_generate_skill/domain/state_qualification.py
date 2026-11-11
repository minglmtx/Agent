"""Exact original evidence selections for environment and normal reset facts."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract, Identifier
from .evidence import EvidenceRef
from .state_scope import StateScope, private_state_ref
from .state_checks import InitialStateSpec, StateChecks
from .reset import ResetPlan
from .lifecycle import RecoveryPlan, ClosureReceipt


class EnvironmentSelection(Contract):
    schema_version: Literal["environment-selection/1"] = "environment-selection/1"
    scope: StateScope
    spec_ref: EvidenceRef
    site_spec_ref: EvidenceRef
    site_started_ref: EvidenceRef
    snapshot_ref: EvidenceRef

    @model_validator(mode="after")
    def references(self) -> Self:
        for ref, schema in (
            (self.spec_ref, "initial-state-spec/1"),
            (self.site_spec_ref, "site-resource-spec/1"),
            (self.site_started_ref, "site-resource-started/1"),
        ):
            private_state_ref(ref, schema)
        if (
            self.snapshot_ref.visibility != "private"
            or self.snapshot_ref.media_type != "application/json"
        ):
            raise ValueError("Environment requires original private snapshot")
        return self


class ResetSelection(Contract):
    schema_version: Literal["reset-selection/1"] = "reset-selection/1"
    environment_selection_ref: EvidenceRef
    plan_ref: EvidenceRef
    restore_request_ref: EvidenceRef
    restore_result_ref: EvidenceRef
    resume_request_ref: EvidenceRef
    resume_result_ref: EvidenceRef
    resume_intent_ref: EvidenceRef
    closure_refs: tuple[EvidenceRef, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def references(self) -> Self:
        for ref, schema in (
            (self.environment_selection_ref, "environment-selection/1"),
            (self.plan_ref, "reset-plan/1"),
            (self.restore_request_ref, "site-task-request/2"),
            (self.restore_result_ref, "site-task-result/1"),
            (self.resume_request_ref, "site-resume-request/1"),
            (self.resume_result_ref, "site-resume-result/1"),
            (self.resume_intent_ref, "site-resume-intent/1"),
        ):
            private_state_ref(ref, schema)
        for ref in self.closure_refs:
            private_state_ref(ref, "closure-receipt/1")
        if len(set(self.closure_refs)) != len(self.closure_refs):
            raise ValueError("Reset cannot duplicate original closures")
        return self


class QualifiedResetChecks(Contract):
    allocation_id: Identifier
    plan: ResetPlan
    spec: InitialStateSpec
    task_recovery: RecoveryPlan
    environment_recovery: RecoveryPlan
    closures: tuple[ClosureReceipt, ...]
    task: StateChecks
    environment: StateChecks
    health: StateChecks
