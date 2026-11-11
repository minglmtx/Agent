"""Selected Map initial records on existing ports with mandatory original authority."""

from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.browser_initialization import BrowserInitialization
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.sites.map.tasks.navigation_initial_observation import (
    NavigationInitialObservationChecks,
)
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority
from lab_generate_skill.sites.map.tasks.overlay_initial_observation import (
    OverlayInitialObservationChecks,
)


def map_initial_observations(
    store: EvidenceStore,
    controls: OperationControls,
    preparations: PreparationRecords,
    authority: InitialObservationAuthority,
    evidence: MapInitialEvidence,
    *,
    initialization: BrowserInitialization,
) -> EvidenceInitialObservations:
    checks: InitialObservationChecks
    if isinstance(initialization, MapNavigationInitialization):
        checks = NavigationInitialObservationChecks(store, evidence, initialization)
    elif isinstance(initialization, MapNativeInitialization):
        checks = OverlayInitialObservationChecks(store, evidence, initialization)
    else:
        raise ValueError(
            "Explicit original Map initialization required; no default selector"
        )
    return EvidenceInitialObservations(
        store,
        controls,
        preparations,
        checks,
        authority,
    )
