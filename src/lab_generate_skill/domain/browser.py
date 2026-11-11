"""Exact protocol action text and recorded browser step returns; no execution.

Protocol adapters validate grammar/name/allowed actions before dispatch. These
records alone prove neither dispatch authorization nor actual physical execution.
"""

from typing import Literal, Self
from pydantic import Field, field_validator, model_validator
from .evidence import EvidenceRef
from .state_scope import StateFact, private_state_ref
from .validation import Contract, Identifier, NonEmptyText


def observation_reference(ref: EvidenceRef) -> None:
    if (ref.visibility, ref.content_schema) != ("public", "observation/1"):
        raise ValueError("Interaction observations require public observation/1")


class BrowserAction(Contract):
    schema_version: Literal["browser-action/1"] = "browser-action/1"
    action_id: Identifier
    protocol_id: Identifier
    name: Identifier
    payload: NonEmptyText = Field(max_length=65536)

    @field_validator("payload")
    @classmethod
    def exact_bounded_utf8(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 65536:
            raise ValueError("Action payload exceeds 65536 UTF-8 bytes")
        return value


class StepResult(StateFact):
    """Recorded actual environment return, including returns with action errors."""

    schema_version: Literal["step-result/1"] = "step-result/1"
    action_id: Identifier
    before_observation_ref: EvidenceRef
    observation_ref: EvidenceRef
    return_ref: EvidenceRef
    terminal: bool

    @model_validator(mode="after")
    def original_return(self) -> Self:
        observation_reference(self.before_observation_ref)
        observation_reference(self.observation_ref)
        private_state_ref(self.return_ref, "browser-step-return/1")
        if self.observation_ref == self.before_observation_ref:
            raise ValueError("Step return must retain its new observation record")
        return self
