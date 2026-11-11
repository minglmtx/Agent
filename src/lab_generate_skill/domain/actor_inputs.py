"""Public first Actor view; private qualification never enters this projection."""

from typing import Literal, Self
from pydantic import model_validator
from .observation import ResolvedObservation
from .skill import CompactSkill
from .task import PublicTask
from .validation import Contract, Identifier


class ActorInput(Contract):
    schema_version: Literal["actor-input/1"] = "actor-input/1"
    source_context_id: Identifier
    task: PublicTask
    skill: CompactSkill
    initial_observation: ResolvedObservation

    @model_validator(mode="after")
    def authoritative_initial_view(self) -> Self:
        observed = self.initial_observation.record
        observed.check_initial(self.task.identity, observed.context_id)
        if observed.attempt_id is None:
            raise ValueError("Actor input requires its actual attempt observation")
        return self
