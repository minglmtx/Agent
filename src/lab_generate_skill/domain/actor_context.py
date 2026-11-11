"""Frozen Actor role configuration and exact prepared input references."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .context_budget import ContextBudgetProfile
from .context_projection import ContextProjectionPolicy
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .validation import Contract


class ActorContextConfiguration(Contract):
    schema_version: Literal["actor-context-configuration/1"] = (
        "actor-context-configuration/1"
    )
    policy: ContextProjectionPolicy
    profiles: tuple[ContextBudgetProfile, ...] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def original_actor_only(self) -> Self:
        if self.policy.role != "actor" or any(
            p.role != "actor" or p.paid or p.provider != "fixed-actor-worker"
            for p in self.profiles
        ):
            raise ValueError("Original unpaid fixed Actor configuration required")
        if len(self.model_dump_json().encode()) > 16 * 1024**2:
            raise ValueError("Actor context configuration exceeds complete byte bound")
        return self


class ActorPreparedInput(Contract):
    schema_version: Literal["actor-prepared-input/1"] = "actor-prepared-input/1"
    input_ref: EvidenceRef
    preparation_ref: EvidenceRef

    @model_validator(mode="after")
    def saved_original_input(self) -> Self:
        private_state_ref(self.input_ref, "actor-model-input/1")
        private_state_ref(self.preparation_ref, "context-preparation/2")
        return self
