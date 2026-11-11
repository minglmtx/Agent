"""Group records on the original delayed site preparation producer."""

from collections.abc import Callable
from lab_generate_skill.adapters.sites.resource import RegisteredSite
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_preparation_state import (
    TaskPreparationState,
)
from lab_generate_skill.adapters.sites.task_preparation_evidence import (
    TaskPreparationEvidence,
)
from lab_generate_skill.adapters.sites.task_preparation_authorities import (
    PreparationEnvironmentAuthority,
    PreparationPublicationAuthority,
)
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.ports.task_preparation import TaskPreparationAuthority
from lab_generate_skill.ports.task_bindings import TaskBindings
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControls
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.sites.gitlab.tasks.group_policy import (
    group_initial_spec,
)
from .gitlab_group_records import (
    group_state_qualifications,
    group_preparation_records,
)
from .deferred_state_records import DeferredPreparationRecords
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON


def gitlab_group_task_preparation(
    plan: TaskExecutionPlan,
    declaration: SiteTaskPreparationPlan,
    spec: SiteResourceSpec,
    site: SiteHandle,
    resources: ResourceJournal,
    evidence: EvidenceStore,
    controls: OperationControls,
    bindings: TaskBindings,
    authority: TaskPreparationAuthority,
    *,
    on_acquired: Callable[[RegisteredSite], None] | None = None,
) -> RecordedSiteTaskPreparation:
    plan = TaskExecutionPlan.model_validate(plan)
    declaration = SiteTaskPreparationPlan.model_validate(declaration)
    spec = SiteResourceSpec.model_validate(spec)
    if any(
        v is None for v in (site, resources, evidence, controls, bindings, authority)
    ):
        raise ValueError(
            "Original Group preparation resources and authorities mandatory"
        )
    group_initial_spec(declaration.scope.task)
    declared = spec.configuration.gitlab_group_inputs
    if declared is not None and declared.scope != declaration.scope:
        raise ValueError("Group preparation changed original declared scope")
    if (
        spec.configuration.site_id != "gitlab"
        or spec.configuration.private_evidence is None
        or spec.configuration.private_evidence.profile != GITLAB_GROUP_PRIVATE_JSON
        or declaration.snapshot_schema != "gitlab-group-recovery/1"
    ):
        raise ValueError("Original Group site and snapshot codec required")
    state = TaskPreparationState()
    io = TaskPreparationEvidence(evidence, state)
    qualifications = group_state_qualifications(
        evidence,
        controls,
        PreparationEnvironmentAuthority(plan, declaration, state, io, authority),
    )
    records = DeferredPreparationRecords(
        lambda: group_preparation_records(
            evidence,
            controls,
            bindings,
            PreparationPublicationAuthority(plan, declaration, state, authority),
        )
    )
    return RecordedSiteTaskPreparation(
        plan,
        declaration,
        spec,
        site,
        resources,
        evidence,
        controls,
        authority,
        qualifications,
        records,
        state,
        on_acquired,
    )
