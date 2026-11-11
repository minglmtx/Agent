"""Local inference identity, frozen sampling and one-way durable call state.

An intent is not an execution permit. Only the adapter that first commits it
under the original lock may invoke its engine; later readers must not replay.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, Self
from pydantic import Field, model_validator
from .evidence import EvidenceRef, EvidenceMetadata
from .generator_model import GeneratorTextCompletion
from .lifecycle import OperationContext, ResourceOwner
from .state_scope import private_state_ref
from .validation import Contract, Identifier, NonEmptyText


def generator_evidence_metadata(schema: str) -> EvidenceMetadata:
    """Original local inference evidence identity shared by prepare and invoke."""
    return EvidenceMetadata(
        media_type="application/json",
        content_schema=schema,
        visibility="private",
        producer="local-generator-v1",
    )


class LocalGeneratorBinding(Contract):
    schema_version: Literal["local-generator-binding/1"] = "local-generator-binding/1"
    owner: ResourceOwner
    source_task_id: Identifier
    release_ref: EvidenceRef
    model_binding_ref: EvidenceRef
    base_parameters_ref: EvidenceRef

    @model_validator(mode="after")
    def frozen_inputs(self) -> Self:
        for ref, schema in (
            (self.release_ref, "release-manifest/1"),
            (self.model_binding_ref, "model-binding/1"),
            (self.base_parameters_ref, "model-parameters/1"),
        ):
            private_state_ref(ref, schema)
        return self


class _SamplingLimits(Contract):
    max_input_tokens: int = Field(ge=1, le=1048576)
    max_new_tokens: int = Field(ge=1, le=65536)
    top_p: float = Field(gt=0, le=1, allow_inf_nan=False)
    enable_thinking: bool


class LocalGeneratorBaseParameters(_SamplingLimits):
    schema_version: Literal["local-generator-base-parameters/1"] = (
        "local-generator-base-parameters/1"
    )


class LocalGeneratorParameters(_SamplingLimits):
    schema_version: Literal["local-generator-parameters/1"] = (
        "local-generator-parameters/1"
    )
    seed: int = Field(ge=0, le=2147483647)
    temperature: float = Field(ge=0, le=2, allow_inf_nan=False)


class LocalGeneratorOutput(Contract):
    text: str
    finish_reason: NonEmptyText
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class LocalGeneratorIntent(Contract):
    schema_version: Literal["local-generator-intent/1"] = "local-generator-intent/1"
    binding: LocalGeneratorBinding
    request_id: Identifier
    request_ref: EvidenceRef
    parameters_ref: EvidenceRef
    operation: OperationContext

    @property
    def key(self) -> str:
        return invocation_key(self.binding, self.request_id)

    @model_validator(mode="after")
    def original_owner(self) -> Self:
        private_state_ref(self.request_ref, "generator-model-request/1")
        private_state_ref(self.parameters_ref, "model-parameters/1")
        op = self.operation
        if (
            (op.run_id, op.owner_id)
            != (self.binding.owner.run_id, self.binding.owner.owner_id)
            or op.mode != "execute"
            or op.attempt_id is not None
            or op.parent_operation_id is not None
            or op.allocation_id is not None
            or op.recovery_ref is not None
        ):
            raise ValueError(
                "Local inference needs its original run-level execute operation"
            )
        if len(self.model_dump_json().encode()) > 8192:
            raise ValueError("Local inference intent exceeds birth record bound")
        return self


def invocation_key(binding: LocalGeneratorBinding, request_id: str) -> str:
    """Same source/request retains one identity across owner/model changes."""
    return hashlib.sha256(
        json.dumps(
            [binding.owner.run_id, binding.source_task_id, request_id],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


class LocalGeneratorSnapshot(Contract):
    schema_version: Literal["local-generator-snapshot/1"] = "local-generator-snapshot/1"
    intent: LocalGeneratorIntent
    response_ref: EvidenceRef | None = None
    fact_ref: EvidenceRef | None = None

    @model_validator(mode="after")
    def completed_reference(self) -> Self:
        if (self.response_ref is None) != (self.fact_ref is None):
            raise ValueError("Completed local inference needs both response and fact")
        if self.response_ref is not None:
            private_state_ref(self.response_ref, "generator-model-response/1")
        if self.fact_ref is not None:
            private_state_ref(self.fact_ref, "local-generator-fact/1")
        return self


class LocalGeneratorFact(Contract):
    schema_version: Literal["local-generator-fact/1"] = "local-generator-fact/1"
    intent: LocalGeneratorIntent
    output: LocalGeneratorOutput
    response_ref: EvidenceRef

    @model_validator(mode="after")
    def response_identity(self) -> Self:
        private_state_ref(self.response_ref, "generator-model-response/1")
        return self


@dataclass(frozen=True)
class GeneratorExecutionObservation:
    """Original facts retained on failure; expected ref does not prove commit."""

    intent: LocalGeneratorIntent
    response_ref: EvidenceRef | None
    completion: GeneratorTextCompletion | None
    fact_ref: EvidenceRef | None
