"""Exact recorded Actor completion and a separate parsing-failure fact."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .actor_prompt import MAX_ACTOR_RESPONSE_BYTES
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .validation import Contract, Identifier, NonEmptyText, Sha256


class ActorTextCompletion(Contract):
    schema_version: Literal["actor-model-response/1"] = "actor-model-response/1"
    generation_id: Identifier
    request_id: Identifier
    input_ref: EvidenceRef
    model_input_sha256: Sha256
    parameters_ref: EvidenceRef
    text: str
    finish_reason: NonEmptyText

    @model_validator(mode="after")
    def original_bounded_completion(self) -> Self:
        private_state_ref(self.input_ref, "actor-model-input/1")
        private_state_ref(self.parameters_ref, "model-parameters/1")
        if len(self.model_dump_json().encode()) > MAX_ACTOR_RESPONSE_BYTES:
            raise ValueError("Actor completion exceeds byte budget")
        return self


class ActorParseFailure(Contract):
    schema_version: Literal["actor-parse-failure/1"] = "actor-parse-failure/1"
    generation_id: Identifier
    response_ref: EvidenceRef
    reason_code: Literal["INVALID_ACTOR_RESPONSE"] = "INVALID_ACTOR_RESPONSE"
    error_type: Identifier
    message: str = Field(max_length=65536)

    @model_validator(mode="after")
    def original_response(self) -> Self:
        private_state_ref(self.response_ref, "actor-model-response/1")
        return self
