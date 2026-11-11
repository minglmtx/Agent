"""Category records on the original registered task preparation producer."""

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
from lab_generate_skill.sites.shopping.tasks.navigation_policy import (
    category_navigation_initial_spec,
)
from .deferred_state_records import DeferredPreparationRecords
from .shopping_category_records import (
    category_state_qualifications,
    category_preparation_records,
)


def shopping_category_task_preparation(
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
            "Original category preparation resources and authorities required"
        )
    category_navigation_initial_spec(declaration.scope.task)
    if (
        spec.configuration.site_id != "shopping"
        or spec.token.owner != declaration.scope.owner
        or spec.token.scope != "batch"
        or declaration.snapshot_schema != "shopping-category-recovery/1"
    ):
        raise ValueError("Original category site, owner and snapshot codec required")
    state = TaskPreparationState()
    io = TaskPreparationEvidence(evidence, state)
    qualifications = category_state_qualifications(
        evidence,
        controls,
        PreparationEnvironmentAuthority(plan, declaration, state, io, authority),
    )
    records = DeferredPreparationRecords(
        lambda: category_preparation_records(
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
