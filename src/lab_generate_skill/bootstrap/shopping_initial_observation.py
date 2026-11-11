"""Consume the original customer browser acquisition; mandatory source authority."""

from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_initial_observation import (
    OrderEtaInitialObservationChecks,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority


def shopping_initial_observations(
    store: EvidenceStore,
    controls: OperationControls,
    preparations: PreparationRecords,
    authority: InitialObservationAuthority,
) -> EvidenceInitialObservations:
    return EvidenceInitialObservations(
        store, controls, preparations, OrderEtaInitialObservationChecks(), authority
    )
