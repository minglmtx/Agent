"""Navigation terminal references; no MapData publication/reference substitution."""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract
from .initial_observation import InitialObservationSelection
from .map_initial_capture import MapInitialEvidence
from .evidence import EvidenceRef
from .state_scope import private_state_ref


class MapNavigationTerminalSelection(Contract):
    schema_version: Literal["map-navigation-terminal-selection/1"] = (
        "map-navigation-terminal-selection/1"
    )
    initial: InitialObservationSelection
    initial_evidence: MapInitialEvidence
    initial_checks_ref: EvidenceRef
    terminal_return_ref: EvidenceRef
    capture_intent_ref: EvidenceRef
    capture_result_ref: EvidenceRef
    trace_ref: EvidenceRef
    trace_snapshot_ref: EvidenceRef

    @model_validator(mode="after")
    def originals(self) -> Self:
        for ref, schema in (
            (self.initial_checks_ref, "initial-state-checks/1"),
            (self.capture_intent_ref, "browser-capture-intent/1"),
            (self.capture_result_ref, "browser-capture-result/1"),
            (self.trace_ref, "interaction-trace/1"),
            (self.trace_snapshot_ref, "trace-journal-snapshot/1"),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json":
                raise ValueError("Original private JSON terminal reference required")
        if (
            self.terminal_return_ref.content_schema
            not in ("browser-initial-return/1", "browser-step-return/1")
            or self.terminal_return_ref.visibility != "private"
            or self.terminal_return_ref.media_type != "application/json"
        ):
            raise ValueError("Original complete terminal browser return required")
        return self
