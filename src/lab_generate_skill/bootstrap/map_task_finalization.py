"""Original Map complete restore/resume/reset on the existing TaskFinalization port."""

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
from lab_generate_skill.sites.map.tasks.state_codec import MapTaskStateCodec
from .map_state_qualification import map_state_qualifications
from lab_generate_skill.adapters.map_artifacts.state_input_transport import (
    MapStateInputsTransport,
)


def map_task_finalization(
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
    *,
    state_inputs: MapStateInputsTransport | None = None,
) -> RecordedTaskFinalization:
    if any(value is None for value in (authority, unstarted, resume)):
        raise ValueError(
            "Actual original cleanup/non-start/resume authorities are mandatory"
        )
    if (
        preparation.declaration.snapshot_schema
        != MapTaskStateCodec(declaration.scope.task).snapshot_schema
    ):
        raise ValueError("Original Map task/snapshot codec required")
    state = TaskFinalizationState()
    qualifications = map_state_qualifications(
        evidence,
        controls,
        FinalizationQualificationAuthority(
            plan, declaration, state, authority, evidence
        ),
        preparation.spec,
        lambda: preparation.site.site,
        state_inputs=state_inputs,
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
