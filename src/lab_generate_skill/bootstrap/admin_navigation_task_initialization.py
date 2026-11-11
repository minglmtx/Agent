"""Admin navigation binding of existing initial-capture and task lifecycle ports.

All owners and permissions are mandatory. This factory performs no acquisition,
source qualification, claim, Actor action or lifecycle execution.
"""

from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
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
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.domain.evidence import EvidenceRef
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
from lab_generate_skill.sites.shopping_admin.tasks.navigation_equivalence import (
    NavigationInitialComparison,
)
from .admin_navigation import admin_navigation_initial_observations


def admin_navigation_task_initialization(
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
    if any(
        value is None
        for value in (
            browser,
            preparations,
            authority,
            state_authority,
            context_authority,
            capture_authority,
            initial_authority,
            evidence,
            controls,
        )
    ):
        raise ValueError(
            "Original Admin navigation resources and authorities are mandatory"
        )
    selected = browser.spec.configuration.initialization
    if not isinstance(selected, AdminNavigationInitialization):
        raise ValueError("Explicit Admin navigation initialization required")
    selected.check(browser.spec.configuration.spec)

    def records(
        intent: EvidenceRef, result: EvidenceRef
    ) -> EvidenceInitialObservations:
        # Capture facts are already persisted by the original capture producer;
        # initial records independently read the unique original worker return.
        return admin_navigation_initial_observations(
            evidence, controls, preparations, initial_authority
        )

    measurements = CapturedTaskInitialMeasurements(
        declaration,
        browser,
        evidence,
        controls,
        capture_authority,
        records,
        collector_id="admin-navigation-page",
        collector_version="1",
    )
    return RecordedTaskInitialization(
        plan,
        declaration,
        declaration_ref,
        browser,
        preparations,
        measurements,
        NavigationInitialComparison(evidence),
        authority,
        state_authority,
        context_authority,
        evidence,
        controls,
        inputs=inputs,
        adoption_checks=adoption_checks,
    )
