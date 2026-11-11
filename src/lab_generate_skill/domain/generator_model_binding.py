"""Pretrained local Generator binding, published after its frozen release.

The manifest pins model/config files; this document references the manifest,
never the reverse. Provider labels are routing, not evidence of loaded bytes.
Checkpoint/adapter-derived bindings require their own implemented contract.
"""

from typing import Literal, Self
from pydantic import model_validator
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .validation import Contract, Identifier, NonEmptyText


class GeneratorModelBinding(Contract):
    schema_version: Literal["generator-model-binding/1"] = "generator-model-binding/1"
    kind: Literal["pretrained"] = "pretrained"
    provider: Literal["transformers"] = "transformers"
    model: NonEmptyText
    release_ref: EvidenceRef
    component_id: Identifier
    model_artifact_id: Identifier
    engine_config_artifact_id: Identifier
    engine_config_ref: EvidenceRef

    @model_validator(mode="after")
    def frozen_references(self) -> Self:
        private_state_ref(self.release_ref, "release-manifest/1")
        private_state_ref(self.engine_config_ref, "generator-engine-config/1")
        if self.model_artifact_id == self.engine_config_artifact_id:
            raise ValueError("Model and engine configuration need distinct artifacts")
        if len(self.model_dump_json().encode()) > 16384:
            raise ValueError("Generator model binding exceeds byte budget")
        return self
