"""Selected category initial capture on the existing initialization lifecycle.

Source/candidate comparison and all permissions are mandatory caller-owned ports.
No ETA initialization, invented source facts or qualification default is supplied.
"""

from lab_generate_skill.adapters.browsergym.initial_measurements import (
    CapturedTaskInitialMeasurements,
)
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
)
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.ports.browser_capture import BrowserCaptureAuthority
from lab_generate_skill.ports.contexts import ContextAuthority
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.state_records import StateAuthority
from lab_generate_skill.ports.task_initialization import (
    TaskInitializationAuthority,
    TaskInitialComparison,
)
from .shopping_category_records import category_initial_observations


def shopping_category_task_initialization(
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
    comparison: TaskInitialComparison,
    evidence: EvidenceStore,
    controls: OperationControls,
    *,
    inputs: TaskInitializationInputs | None = None,
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
            comparison,
            evidence,
            controls,
        )
    ):
        raise ValueError(
            "Original category resources, measurements and authorities required"
        )
    selected = browser.spec.configuration.initialization
    if not isinstance(selected, ShoppingCategoryInitialization):
        raise ValueError("Explicit original category initialization required")
    selected.check(browser.spec.configuration.spec)

    def records(
        intent: EvidenceRef, result: EvidenceRef
    ) -> EvidenceInitialObservations:
        # The fixed capture producer persists its original passive first-return
        # evidence. Existing initial records independently verify that return.
        return category_initial_observations(
            evidence, controls, preparations, initial_authority
        )

    measurements = CapturedTaskInitialMeasurements(
        declaration,
        browser,
        evidence,
        controls,
        capture_authority,
        records,
        collector_id="shopping-category-navigation-page",
        collector_version="1",
    )
    return RecordedTaskInitialization(
        plan,
        declaration,
        declaration_ref,
        browser,
        preparations,
        measurements,
        comparison,
        authority,
        state_authority,
        context_authority,
        evidence,
        controls,
        inputs=inputs,
    )
