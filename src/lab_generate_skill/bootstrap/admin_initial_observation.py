"""Fixed selected-task initial checks; callers supply all actual authorities."""

from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_initial_observation import (
    ProductInitialObservationChecks,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority


def admin_initial_observations(
    store: EvidenceStore,
    controls: OperationControls,
    preparations: PreparationRecords,
    authority: InitialObservationAuthority,
) -> EvidenceInitialObservations:
    return EvidenceInitialObservations(
        store, controls, preparations, ProductInitialObservationChecks(), authority
    )
