"""Public Generator inputs, projected Teacher inputs and bound candidate output.

No private TaskBinding, baseline, claim, budget or dependency container enters
GenerationInput. Teacher receives only a versioned allowed projection. Actual
request bytes/provenance still require the model adapter and independent audit.
"""

from typing import Any, Literal, Self

from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .actor_versions import actor_version_fields, actor_version_output
from .state_scope import private_state_ref

from .evidence import EvidenceRef
from .skill import CompactSkill
from .generator_actor_capabilities import GeneratorActorCapabilities
from .task import PublicTask
from .validation import Contract, Identifier, Sha256


class PublicConstructionContext(Contract):
    schema_version: Literal["public-construction-context/1"] = (
        "public-construction-context/1"
    )
    context_id: Identifier
    task: PublicTask
    initial_observation_ref: EvidenceRef

    @model_validator(mode="after")
    def public_observation(self) -> Self:
        if (
            self.initial_observation_ref.visibility != "public"
            or self.initial_observation_ref.content_schema != "observation/1"
        ):
            raise ValueError(
                "Generator initial observation must be public observation/1"
            )
        return self


class GenerationInput(Contract):
    schema_version: Literal["generation-input/1", "generation-input/2"] = (
        "generation-input/1"
    )
    actor_capabilities: GeneratorActorCapabilities | None = None
    request_id: Identifier
    context: PublicConstructionContext
    retrieved_skills: tuple[CompactSkill, ...] = Field(min_length=6, max_length=6)
    candidate_index: int = Field(ge=0, le=3)
    resample_index: int = Field(ge=0, le=4)
    seed: int = Field(ge=0, le=2147483647)
    temperature: float = Field(ge=0, le=2, allow_inf_nan=False)

    @model_serializer(mode="wrap")
    def versioned_capabilities(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        return actor_version_output(
            self,
            handler,
            self.schema_version == "generation-input/1",
            ("actor_capabilities",),
        )

    @model_validator(mode="after")
    def selected_actor_contract(self) -> Self:
        old = self.schema_version == "generation-input/1"
        actor_version_fields(
            self, old, ("actor_capabilities",), record_name="Generator input"
        )
        if old != (self.actor_capabilities is None):
            raise ValueError(
                "Generator input2 requires selected public Actor capabilities; input1 forbids them"
            )
        return self


class RevisionInput(Contract):
    schema_version: Literal["revision-input/1"] = "revision-input/1"
    request_id: Identifier
    teacher_round: int = Field(ge=1, le=3)
    seed: int = Field(ge=0, le=2147483647)
    projection_ref: EvidenceRef

    @model_validator(mode="after")
    def permitted_projection(self) -> Self:
        if (
            self.projection_ref.visibility != "teacher"
            or self.projection_ref.content_schema != "teacher-input/1"
        ):
            raise ValueError(
                "Teacher requires its allowed projection, not raw private evidence"
            )
        return self


class CandidateResponse(Contract):
    request_id: Identifier
    input_sha256: Sha256
    parameters_sha256: Sha256
    skill: CompactSkill
    response_ref: EvidenceRef

    @model_validator(mode="after")
    def private_response(self) -> Self:
        if self.response_ref.visibility != "private":
            raise ValueError("Raw model response evidence must remain private")
        return self


class GeneratedCandidate(CandidateResponse):
    schema_version: Literal["generated-candidate/1"] = "generated-candidate/1"


class RevisionResult(CandidateResponse):
    schema_version: Literal["revision-result/1", "revision-result/2"] = (
        "revision-result/1"
    )
    execution_ref: EvidenceRef | None = None

    @model_serializer(mode="wrap")
    def versioned_fields(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        return actor_version_output(
            self,
            handler,
            self.schema_version == "revision-result/1",
            ("execution_ref",),
        )

    @model_validator(mode="after")
    def original_revision_execution(self) -> Self:
        old = self.schema_version == "revision-result/1"
        actor_version_fields(
            self, old, ("execution_ref",), record_name="Teacher revision"
        )
        if old != (self.execution_ref is None):
            raise ValueError(
                "Teacher revision v2 requires original execution evidence; v1 forbids it"
            )
        if self.execution_ref is not None:
            private_state_ref(self.execution_ref, "teacher-revision-execution/1")
            if (
                self.execution_ref.media_type != "application/json"
                or not 0 < self.execution_ref.size_bytes <= 2 * 1024**2
            ):
                raise ValueError("Bounded complete private Teacher execution required")
        return self
