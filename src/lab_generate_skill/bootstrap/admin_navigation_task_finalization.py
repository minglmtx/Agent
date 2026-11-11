"""Navigation complete restore/resume/Reset on the existing finalization port."""

from collections.abc import Callable
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.task_finalization import (
    OriginalTaskBrowserFinalizer,
)
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_finalization import RecordedTaskFinalization
from lab_generate_skill.adapters.sites.task_finalization_state import (
    TaskFinalizationState,
)
from lab_generate_skill.adapters.sites.task_finalization_authorities import (
    FinalizationQualificationAuthority,
    FinalizationResetAuthority,
)
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControls
from lab_generate_skill.ports.task_finalization import (
    TaskFinalizationAuthority,
    UnstartedTaskBrowserAuthority,
)
from lab_generate_skill.ports.site_resume import SiteResumeAuthority
from lab_generate_skill.sites.shopping_admin.tasks.navigation_state_policy import (
    navigation_initial_state_spec,
)
from .admin_navigation import admin_navigation_state_qualifications


def admin_navigation_task_finalization(
    plan: TaskExecutionPlan,
    declaration: TaskFinalizationPlan,
    declaration_ref: EvidenceRef,
    reset: ResetPlan,
    preparation: RecordedSiteTaskPreparation,
    browser: Callable[[], RetainedBrowserResource | None],
    resources: ResourceJournal,
    known_closure: Callable[[], EvidenceRef | None],
    authority: TaskFinalizationAuthority,
    unstarted: UnstartedTaskBrowserAuthority,
    resume: SiteResumeAuthority,
    evidence: EvidenceStore,
    controls: OperationControls,
) -> RecordedTaskFinalization:
    if any(
        value is None
        for value in (
            preparation,
            browser,
            resources,
            known_closure,
            authority,
            unstarted,
            resume,
            evidence,
            controls,
        )
    ):
        raise ValueError("Original Admin cleanup/nonstart/resume authorities mandatory")
    navigation_initial_state_spec(declaration.scope.task)
    if (
        preparation.spec.configuration.site_id != "shopping_admin"
        or preparation.declaration.snapshot_schema != "admin-navigation-recovery/1"
    ):
        raise ValueError("Original Admin navigation preparation and snapshot required")
    state = TaskFinalizationState()
    qualifications = admin_navigation_state_qualifications(
        evidence,
        controls,
        FinalizationQualificationAuthority(
            plan, declaration, state, authority, evidence
        ),
    )
    states = EvidenceStateRecords(
        evidence,
        controls,
        FinalizationResetAuthority(
            plan, declaration, state, authority, qualifications.checks, controls
        ),
    )
    owner = OriginalTaskBrowserFinalizer(
        browser, resources, unstarted, evidence, known_closure
    )
    return RecordedTaskFinalization(
        plan,
        declaration,
        declaration_ref,
        reset,
        preparation,
        owner,
        qualifications,
        states,
        authority,
        resume,
        evidence,
        controls,
        state,
    )
