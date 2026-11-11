"""Three original immutable Actor acquisition objects; never live authority."""

import hashlib
from typing import Self
from pydantic import Field, model_validator
from .validation import Contract
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .local_actor import LocalActorBinding
from .actor_resource import ActorResourceSpec
from .resource_acquisition import ResourceAcquisitionIntent

ACTOR_ACQUISITION_BODY_LIMIT = 2 * 1024**2


class ActorAcquisitionInputs(Contract):
    binding: LocalActorBinding
    intent_ref: EvidenceRef

    @model_validator(mode="after")
    def references(self) -> Self:
        private_state_ref(self.intent_ref, "resource-acquisition-intent/1")
        private_state_ref(self.binding.spec_ref, "actor-resource-spec/1")
        private_state_ref(self.binding.acquired_ref, "actor-resource-fact/1")
        return self

    def supported(self) -> bool:
        return all(
            0 < ref.size_bytes <= ACTOR_ACQUISITION_BODY_LIMIT
            for ref in (
                self.intent_ref,
                self.binding.spec_ref,
                self.binding.acquired_ref,
            )
        )


class ActorAcquisitionBodies(Contract):
    selection: ActorAcquisitionInputs
    intent_json: str = Field(min_length=1, max_length=ACTOR_ACQUISITION_BODY_LIMIT)
    spec_json: str = Field(min_length=1, max_length=ACTOR_ACQUISITION_BODY_LIMIT)
    acquired_json: str = Field(min_length=1, max_length=ACTOR_ACQUISITION_BODY_LIMIT)

    @model_validator(mode="after")
    def original(self) -> Self:
        if not self.selection.supported():
            raise ValueError(
                "Original Actor body proof exceeds declared complete bound"
            )
        binding = self.selection.binding
        for ref, text in (
            (self.selection.intent_ref, self.intent_json),
            (binding.spec_ref, self.spec_json),
            (binding.acquired_ref, self.acquired_json),
        ):
            raw = text.encode()
            if (len(raw), hashlib.sha256(raw).hexdigest()) != (
                ref.size_bytes,
                ref.sha256,
            ):
                raise ValueError(
                    "Actor proof omitted or changed complete original bytes"
                )
        intent = ResourceAcquisitionIntent.model_validate_json(self.intent_json)
        spec = ActorResourceSpec.model_validate_json(self.spec_json)
        if (
            intent.token != binding.resource
            or intent.configuration_ref != binding.spec_ref
            or spec.token != binding.resource
            or spec.release_ref != binding.release_ref
            or spec.model_binding_ref != binding.model_binding_ref
        ):
            raise ValueError(
                "Actor acquisition bodies changed original resource/binding"
            )
        return self
