"""Generator inference envelopes; routing identities never enter message bytes.

generation_input_sha256 identifies the public role object used by construction.
model_input_sha256 identifies the actual rendered message payload, separately.
Completion records preserve original text even when empty, invalid or truncated.
"""

import hashlib
import json
from typing import Literal, Self
from pydantic import Field, model_validator
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .validation import Contract, Identifier, NonEmptyText, Sha256

MAX_GENERATOR_INPUT_BYTES = 8 * 1024 * 1024
MAX_GENERATOR_RESPONSE_BYTES = 1024 * 1024


class GeneratorMessage(Contract):
    role: Literal["system", "user"]
    content: NonEmptyText


class GeneratorModelRequest(Contract):
    schema_version: Literal["generator-model-request/1"] = "generator-model-request/1"
    request_id: Identifier
    generation_input_sha256: Sha256
    prompt_version: Literal[
        "webarena-generator-v6-actor-capabilities",
        "webarena-generator-v7-selected-actor",
    ]
    messages: tuple[GeneratorMessage, GeneratorMessage]
    seed: int = Field(ge=0, le=2147483647)
    temperature: float = Field(ge=0, le=2, allow_inf_nan=False)

    def input_bytes(self) -> bytes:
        return json.dumps(
            {"messages": [m.model_dump() for m in self.messages]}, ensure_ascii=False
        ).encode()

    @property
    def model_input_sha256(self) -> str:
        return hashlib.sha256(self.input_bytes()).hexdigest()

    @model_validator(mode="after")
    def ordered_messages(self) -> Self:
        if tuple(m.role for m in self.messages) != ("system", "user"):
            raise ValueError("Generator needs one system message and one user message")
        if len(self.input_bytes()) > MAX_GENERATOR_INPUT_BYTES:
            raise ValueError("Generator messages exceed byte budget")
        return self


class GeneratorTextCompletion(Contract):
    schema_version: Literal["generator-text-completion/1"] = (
        "generator-text-completion/1"
    )
    request_id: Identifier
    generation_input_sha256: Sha256
    model_input_sha256: Sha256
    parameters_ref: EvidenceRef
    text: str
    finish_reason: NonEmptyText

    @model_validator(mode="after")
    def bounded_record(self) -> Self:
        private_state_ref(self.parameters_ref, "model-parameters/1")
        if len(self.model_dump_json().encode()) > MAX_GENERATOR_RESPONSE_BYTES:
            raise ValueError("Generator completion exceeds byte budget")
        return self
