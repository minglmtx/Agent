"""Selected navigation initialization on the existing task/capture/state ports."""

from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
)


from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.adapters.browsergym.initial_measurements import (
    CapturedTaskInitialMeasurements,
)
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.ports.browser_capture import BrowserCaptureAuthority
from lab_generate_skill.ports.initial_adoption import InitialAdoptionAuthority
from lab_generate_skill.ports.contexts import ContextAuthority
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.state_records import StateAuthority
from lab_generate_skill.ports.task_initialization import TaskInitializationAuthority
from lab_generate_skill.sites.map.tasks.navigation_equivalence import (
    NavigationInitialComparison,
)
from .map_initial_observation import map_initial_observations


def map_navigation_task_initialization(
    plan: TaskExecutionPlan,
    declaration: TaskInitializationPlan,
    declaration_ref: EvidenceRef,
    browser: RetainedBrowserResource,
    preparations: PreparationRecords,
    authority: TaskInitializationAuthority,
    state_authority: StateAuthority,
    context_authority: ContextAuthority,
    capture_authority: BrowserCaptureAuthority,
    initial_authority: InitialObservationAuthority,
    evidence: EvidenceStore,
    controls: OperationControls,
    *,
    inputs: TaskInitializationInputs | None = None,
    adoption_checks: InitialAdoptionAuthority | None = None,
) -> RecordedTaskInitialization:
    selected = browser.spec.configuration.initialization
    if not isinstance(selected, MapNavigationInitialization):
        raise ValueError("Explicit selected navigation initialization required")
    if capture_authority is None or initial_authority is None:
        raise ValueError("Original capture and initial authorities are mandatory")

    def records(
        intent: EvidenceRef, result: EvidenceRef
    ) -> EvidenceInitialObservations:
        return map_initial_observations(
            evidence,
            controls,
            preparations,
            initial_authority,
            MapInitialEvidence(intent_ref=intent, result_ref=result),
            initialization=selected,
        )

    measurements = CapturedTaskInitialMeasurements(
        declaration,
        browser,
        evidence,
        controls,
        capture_authority,
        records,
        collector_id="map-navigation-initial",
        collector_version="1",
    )
    return RecordedTaskInitialization(
        plan,
        declaration,
        declaration_ref,
        browser,
        preparations,
        measurements,
        NavigationInitialComparison(),
        authority,
        state_authority,
        context_authority,
        evidence,
        controls,
        inputs=inputs,
        adoption_checks=adoption_checks,
    )
