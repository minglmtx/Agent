"""Private bounded Actor-loop request; only its public projection reaches a model."""

from typing import Literal, Self, Any
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .actor_versions import actor_version_fields, actor_version_output
from .actor_execution_window import ActorGenerationBudgets
from .browser import observation_reference
from .evidence import EvidenceRef
from .lifecycle import AllocationToken, OperationContext
from .optional_policies import InactivePolicy
from .skill import CompactSkill
from .state_scope import StateScope, private_state_ref
from .task import PublicTask
from .validation import Contract, Identifier


class ActorRunRequest(Contract):
    schema_version: Literal["actor-run-request/1", "actor-run-request/2"] = (
        "actor-run-request/1"
    )
    candidate_id: Identifier | None = None
    revision_round: int | None = Field(default=None, ge=0, le=3)
    context_configuration_ref: EvidenceRef | None = None
    scope: StateScope
    task: PublicTask
    skill: CompactSkill
    memory: InactivePolicy
    initial_observation_ref: EvidenceRef
    model_allocation: AllocationToken
    browser_allocation: AllocationToken
    parameters_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=10000)
    operation: OperationContext
    generation_seconds: int = Field(ge=1, le=600)
    interaction_seconds: int = Field(ge=1, le=180)
    cleanup_seconds: int = Field(ge=1, le=60)

    generation_budgets: ActorGenerationBudgets | None = None

    @model_serializer(mode="wrap")
    def wire_version(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result = actor_version_output(
            self,
            handler,
            self.schema_version == "actor-run-request/1",
            ("candidate_id", "revision_round", "context_configuration_ref"),
        )

        if self.generation_budgets is None:
            result.pop("generation_budgets", None)
        return result

    @model_validator(mode="after")
    def original_attempt_and_resources(self) -> Self:
        scope, op = self.scope, self.operation
        if (
            self.generation_budgets is not None
            and self.generation_budgets.execution_seconds != self.generation_seconds
        ):
            raise ValueError(
                "Selected actual-call window differs from original generation duration"
            )
        new = self.schema_version == "actor-run-request/2"
        actor_version_fields(
            self,
            not new,
            ("candidate_id", "revision_round", "context_configuration_ref"),
        )
        if new != all(
            v is not None
            for v in (
                self.candidate_id,
                self.revision_round,
                self.context_configuration_ref,
            )
        ) or (
            not new
            and any(
                v is not None
                for v in (
                    self.candidate_id,
                    self.revision_round,
                    self.context_configuration_ref,
                )
            )
        ):
            raise ValueError(
                "Actor v2 requires original candidate/round/context config; v1 forbids them"
            )
        if self.context_configuration_ref is not None:
            private_state_ref(
                self.context_configuration_ref, "actor-context-configuration/1"
            )
        observation_reference(self.initial_observation_ref)
        if self.task.identity != scope.task or (
            op.run_id,
            op.owner_id,
            op.attempt_id,
            op.mode,
        ) != (scope.owner.run_id, scope.owner.owner_id, scope.attempt_id, "execute"):
            raise ValueError(
                "Actor loop must retain the original task/attempt execute scope"
            )
        if any(
            token.owner != scope.owner
            for token in (self.model_allocation, self.browser_allocation)
        ):
            raise ValueError("Actor resources must retain the original owner")
        if (
            self.model_allocation.resource_kind,
            self.model_allocation.scope,
            self.model_allocation.attempt_id,
        ) != ("actor", "batch", None):
            raise ValueError("Actor model must be its declared batch resource")
        if (
            self.browser_allocation.resource_kind,
            self.browser_allocation.scope,
            self.browser_allocation.attempt_id,
        ) != ("browser", "attempt", scope.attempt_id):
            raise ValueError("Actor browser must be the original attempt resource")
        if self.model_allocation.allocation_id == self.browser_allocation.allocation_id:
            raise ValueError("Actor model and browser allocations must differ")
        for ref in self.parameters_refs:
            private_state_ref(ref, "model-parameters/1")
        return self


class ActorStop(Contract):
    schema_version: Literal["trace-stop/1"] = "trace-stop/1"
    request_ref: EvidenceRef
    scope: StateScope
    reason: Literal[
        "finished",
        "generation_limit",
        "interaction_limit",
        "cancelled",
        "error",
        "uncertain",
    ]
    generations: int = Field(ge=0)
    interactions: int = Field(ge=0)
    final_observation_ref: EvidenceRef

    @model_validator(mode="after")
    def original_run(self) -> Self:
        if (
            self.request_ref.visibility != "private"
            or self.request_ref.content_schema
            not in ("actor-run-request/1", "actor-run-request/2")
        ):
            raise ValueError("Original versioned private Actor request required")
        observation_reference(self.final_observation_ref)
        if self.interactions > self.generations:
            raise ValueError("Actor interactions cannot exceed actual generations")
        return self
