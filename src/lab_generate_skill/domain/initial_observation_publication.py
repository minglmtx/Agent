"""Exact published initial checks and their same-call immutable input graph."""

from dataclasses import dataclass
from .evidence import EvidenceRef
from .baseline import InitialStateChecks
from .initial_observation import InitialObservationInputs
from .preparation import PreparationReceipt


@dataclass(frozen=True)
class PublishedInitialObservation:
    reference: EvidenceRef
    value: InitialStateChecks
    inputs: InitialObservationInputs
    preparation: PreparationReceipt
