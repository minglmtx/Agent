"""Read-only initial-check production, with mandatory provenance/policy authority."""

from typing import Protocol
from lab_generate_skill.domain.initial_observation import (
    InitialObservationSelection,
    InitialObservationInputs,
)
from lab_generate_skill.domain.baseline import InitialStateChecks
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from .lifecycle import OperationControl


class InitialObservationReads(Protocol):
    def load(
        self,
        selection: InitialObservationSelection,
        operation: OperationContext,
        control: OperationControl,
    ) -> InitialObservationInputs:
        """Original immutable initial facts; current permissions remain separate."""
        ...


class InitialObservationChecks(Protocol):
    def check(
        self, inputs: InitialObservationInputs, control: OperationControl
    ) -> StateChecks: ...


class InitialObservationAuthority(Protocol):
    def verify(
        self,
        inputs: InitialObservationInputs,
        checks: StateChecks,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Verify original journal/worker, policy, source, ordering and exclusivity.

        Historical validation cannot issue new execution permission. No browser
        calls, default approval or inferred full environment/reset qualification.
        """
        ...


class InitialObservationRecords(Protocol):
    def publish(
        self, selection: InitialObservationSelection, operation: OperationContext
    ) -> EvidenceRef: ...
    def load(
        self,
        selection: InitialObservationSelection,
        reference: EvidenceRef,
        operation: OperationContext,
    ) -> InitialStateChecks: ...
