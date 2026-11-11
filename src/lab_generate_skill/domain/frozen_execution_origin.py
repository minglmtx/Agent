"""Explicit immutable origin for one corrected Actor-to-close validation."""

from typing import Literal, Self
from pydantic import model_validator
from .evidence import EvidenceRef
from .source_stage_validation import SourceStageValidation
from .state_scope import private_state_ref
from .validation import Contract


class FrozenExecutionOrigin(Contract):
    schema_version: Literal["frozen-execution-origin/1"] = "frozen-execution-origin/1"
    validation: SourceStageValidation
    parent_source_ref: EvidenceRef

    @model_validator(mode="after")
    def original_manifest(self) -> Self:
        private_state_ref(self.parent_source_ref, "execution-task-source/1")
        return self
