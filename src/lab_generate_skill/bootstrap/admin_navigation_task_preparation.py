"""Navigation records on the original delayed Site preparation producer."""

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
from lab_generate_skill.sites.shopping_admin.tasks.navigation_state_policy import (
    navigation_initial_state_spec,
)
from .admin_navigation import (
    admin_navigation_state_qualifications,
    admin_navigation_preparation_records,
)
from .deferred_state_records import DeferredPreparationRecords


def admin_navigation_task_preparation(
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
            "Original Admin preparation resources and authorities mandatory"
        )
    navigation_initial_state_spec(declaration.scope.task)
    inputs = spec.configuration.admin_navigation_inputs
    if (
        spec.configuration.site_id != "shopping_admin"
        or spec.configuration.schema_version != "site-worker-configuration/7"
        or inputs is None
        or inputs.scope != declaration.scope
        or declaration.snapshot_schema != "admin-navigation-recovery/1"
    ):
        raise ValueError("Original Admin navigation site and snapshot codec required")
    state = TaskPreparationState()
    io = TaskPreparationEvidence(evidence, state)
    qualifications = admin_navigation_state_qualifications(
        evidence,
        controls,
        PreparationEnvironmentAuthority(plan, declaration, state, io, authority),
    )
    records = DeferredPreparationRecords(
        lambda: admin_navigation_preparation_records(
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
