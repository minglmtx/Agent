"""Exact original terminal capture and initial binding, not a DB query or verdict."""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract
from .initial_observation import InitialObservationSelection
from .evidence import EvidenceRef
from .state_scope import private_state_ref


class MapTerminalSelection(Contract):
    schema_version: Literal["map-terminal-selection/1"] = "map-terminal-selection/1"
    initial: InitialObservationSelection
    capture_intent_ref: EvidenceRef
    capture_result_ref: EvidenceRef
    original_reference_ref: EvidenceRef

    @model_validator(mode="after")
    def references(self) -> Self:
        for ref, schema in (
            (self.capture_intent_ref, "browser-capture-intent/1"),
            (self.capture_result_ref, "browser-capture-result/1"),
            (self.original_reference_ref, "map-native-layer-proof/1"),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json":
                raise ValueError("Original private Map JSON reference required")
        return self
