"""Explicit engineering Actor context selection; no source or fee permission."""

from typing import Literal, Self
from pydantic import Field, field_validator, model_validator
from .validation import Contract, Identifier
from .skill import CompactSkill
from .optional_policies import InactivePolicy
from .actor_projection import ActorProjectionConfiguration
from .evidence import EvidenceRef
from .state_scope import private_state_ref


class EngineeringActorPolicy(Contract):
    schema_version: Literal["engineering-execution-policy/3"] = (
        "engineering-execution-policy/3"
    )
    engineering_only: Literal[True] = True
    skill: CompactSkill
    memory: InactivePolicy
    max_generations: int = Field(ge=1, le=10000)
    max_interactions: int = Field(ge=1, le=10000)
    actor_projection: ActorProjectionConfiguration
    actor_context_ref: EvidenceRef
    candidate_id: Identifier
    revision_round: int = Field(ge=0, le=3)

    @field_validator("engineering_only", mode="before")
    @classmethod
    def exact_engineering_flag(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("Actual engineering boolean required")
        return value

    @model_validator(mode="after")
    def original_context(self) -> Self:
        private_state_ref(self.actor_context_ref, "actor-context-configuration/1")
        if self.actor_context_ref.media_type != "application/json":
            raise ValueError("Frozen complete Actor context JSON required")
        if self.max_interactions > self.max_generations:
            raise ValueError("Interactions cannot exceed original generation budget")
        return self
