"""Transport of already captured public facts; never opens a browser.

Publishing is attempt-level execute. Reading is run-level or the matching
attempt, including independent bounded cleanup. Stored facts do not prove
baseline equivalence, capture completeness or production permission.
"""

from typing import Protocol, runtime_checkable
from .evidence import EvidenceReader

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation, ResolvedObservation


class ObservationLoader(Protocol):
    def load(
        self, reference: EvidenceRef, op: OperationContext
    ) -> ResolvedObservation: ...


@runtime_checkable
class ObservationInputReads(Protocol):
    def with_inputs(self, inputs: EvidenceReader) -> ObservationLoader:
        """Retain original observation parsing and attempt checks over exact bytes."""
        ...


class Observations(ObservationLoader, Protocol):
    def publish(
        self, observation: Observation, op: OperationContext
    ) -> EvidenceRef: ...
