"""Attempt-bound live trace plan and explicit bounded storage reservations."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .browser import observation_reference
from .errors import OwnershipConflict
from .evidence import EvidenceRef
from .execution import AttemptBinding
from .state_scope import StateScope
from .validation import Contract


class TraceCapacity(Contract):
    schema_version: Literal["trace-capacity/1"] = "trace-capacity/1"
    max_events: int = Field(ge=5, le=50001)
    max_bytes: int = Field(ge=1, le=8 * 1024 * 1024)
    max_event_bytes: int = Field(ge=1, le=8 * 1024 * 1024)
    max_trace_bytes: int = Field(ge=1, le=8 * 1024 * 1024)

    @model_validator(mode="after")
    def minimum_turn_reserve(self) -> Self:
        if 6 * (self.max_event_bytes + 1) > min(self.max_bytes, self.max_trace_bytes):
            raise ValueError(
                "Capacity must leave room for one full turn and trace envelope"
            )
        return self


class TracePlan(Contract):
    schema_version: Literal["trace-plan/1"] = "trace-plan/1"
    binding: AttemptBinding
    scope: StateScope
    initial_observation_ref: EvidenceRef
    max_generations: int = Field(ge=1, le=10000)
    max_interactions: int = Field(ge=1, le=10000)
    capacity: TraceCapacity

    @model_validator(mode="after")
    def exact_attempt(self) -> Self:
        observation_reference(self.initial_observation_ref)
        if (self.binding.run.owner, self.binding.task, self.binding.attempt_id) != (
            self.scope.owner,
            self.scope.task,
            self.scope.attempt_id,
        ):
            raise OwnershipConflict(
                "Live trace must retain the full original attempt binding"
            )
        return self
