"""Group binding of existing initial-capture and task lifecycle ports.

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
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.ports.browser_capture import BrowserCaptureAuthority
from lab_generate_skill.ports.contexts import ContextAuthority
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.state_records import StateAuthority
from lab_generate_skill.ports.task_initialization import TaskInitializationAuthority
from lab_generate_skill.sites.gitlab.tasks.group_equivalence import (
    GroupInitialComparison,
)
from lab_generate_skill.sites.gitlab.tasks.group_reads import GroupStateReads
from lab_generate_skill.sites.gitlab.tasks.group_initial_capture import (
    GroupTaskInitialChecks,
    group_initial_capture_request,
)
from .gitlab_group_capture import load_group_capture
from .gitlab_group_initial_capture import GroupInitialNativeCapture


class GroupTaskInitialization(RecordedTaskInitialization):
    """The existing lifecycle with its original Group before-capture owner."""

    native_before: GroupInitialNativeCapture


def gitlab_group_task_initialization(
    plan: TaskExecutionPlan,
    declaration: TaskInitializationPlan,
    declaration_ref: EvidenceRef,
    browser: RetainedBrowserResource,
    preparation: RecordedSiteTaskPreparation,
    authority: TaskInitializationAuthority,
    state_authority: StateAuthority,
    context_authority: ContextAuthority,
    capture_authority: BrowserCaptureAuthority,
    initial_authority: InitialObservationAuthority,
    evidence: EvidenceStore,
    controls: OperationControls,
    *,
    inputs: TaskInitializationInputs | None = None,
) -> GroupTaskInitialization:
    plan = TaskExecutionPlan.model_validate(plan)
    declaration = TaskInitializationPlan.model_validate(declaration)
    if not isinstance(preparation, RecordedSiteTaskPreparation):
        raise TypeError("Original typed Group preparation producer required")
    preparations = preparation.records
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
        raise ValueError("Original Group resources and authorities are mandatory")
    selected = browser.spec.configuration.initialization
    if not isinstance(selected, GitlabGroupInitialization):
        raise ValueError("Explicit Group initialization required")
    selected.check(browser.spec.configuration.spec)
    if (
        preparation.plan != plan
        or preparation.state.phase != "prepared"
        or preparation.state.result_ref != declaration.prepared_result_ref
        or preparation.state.prepare_request is None
    ):
        raise ValueError(
            "Confirmed original Group preparation required before initialization"
        )
    # Validate the derived native operation before browser acquisition.
    group_initial_capture_request(declaration, preparation.state.prepare_request)
    native = GroupInitialNativeCapture(preparation, lambda: initializer)

    def records(
        intent: EvidenceRef, result: EvidenceRef
    ) -> EvidenceInitialObservations:
        before = native.record(controls.bind(declaration.initial_operation))
        return EvidenceInitialObservations(
            evidence,
            controls,
            preparations,
            GroupTaskInitialChecks(
                evidence, declaration, intent, result, before, load_group_capture
            ),
            initial_authority,
        )

    measurements = CapturedTaskInitialMeasurements(
        declaration,
        browser,
        evidence,
        controls,
        capture_authority,
        records,
        collector_id="gitlab-page-health",
        collector_version="1",
    )
    initializer = GroupTaskInitialization(
        plan,
        declaration,
        declaration_ref,
        browser,
        preparations,
        measurements,
        GroupInitialComparison(GroupStateReads(evidence, load_group_capture)),
        authority,
        state_authority,
        context_authority,
        evidence,
        controls,
        inputs=inputs,
    )
    initializer.native_before = native
    return initializer
