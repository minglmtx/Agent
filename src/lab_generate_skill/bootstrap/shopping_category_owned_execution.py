"""Shopping category codecs on the existing claimed-owner task assembly; no live defaults."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from .shopping_category_claimed_authority import (
    CategoryNavigationClaimedSiteAuthority,
)
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.adapters.sites.execution_task_authority import (
    OriginalExecutionTaskAuthority,
)
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_resource_owner import (
    OriginalTaskResourceOwner,
)
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.trace_plan import TraceCapacity
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControl,
    OperationControls,
    ResourceJournal,
)
from lab_generate_skill.ports.task_bindings import TaskBindings
from lab_generate_skill.sites.shopping.tasks.navigation_equivalence import (
    CategoryNavigationInitialComparison,
)
from lab_generate_skill.sites.shopping.tasks.navigation_browser_checks import (
    CategoryNavigationBrowserChecks,
)
from .shopping_category_closed_source import ClosedCategoryNavigationSourceContexts
from .shopping_category_initial_capture import CapturedCategoryNavigationInitialChecks
from .shopping_category_task_execution import (
    shopping_category_task_execution,
    CategoryNavigationExecutionRuntime,
    CategoryNavigationTaskExecution,
)
from .task_execution_bindings import (
    TaskExecutionDeclarations,
    TaskExecutionResources,
    ExecutionTaskAuthorities,
)
from .owned_task_execution import (
    OwnedTaskExecution,
    OwnedTaskPolicy,
    TaskBrowserDeclarations,
    owned_task_execution,
)


@dataclass(frozen=True)
class OwnedCategoryNavigationExecution(
    OwnedTaskExecution[CategoryNavigationTaskExecution]
):
    pass


def shopping_category_owned_execution(
    declarations: TaskExecutionDeclarations,
    owner: ClaimedRunResourceOwner,
    source: OriginalExecutionTaskSource,
    model: ActorExecutionScope,
    site_spec: SiteResourceSpec,
    site_acquisition: OperationContext,
    browser_declarations: Callable[
        [RecordedSiteTaskPreparation, OperationContext, OperationControl],
        TaskBrowserDeclarations,
    ],
    *,
    journal: ResourceJournal,
    bindings: TaskBindings,
    controls: OperationControls,
    clock: Clock,
    trace_root: Path,
    calls_root: Path,
    trace_capacity: TraceCapacity,
) -> OwnedCategoryNavigationExecution:
    if (
        not isinstance(declarations, TaskExecutionDeclarations)
        or not isinstance(site_spec, SiteResourceSpec)
        or not isinstance(owner, ClaimedRunResourceOwner)
        or not isinstance(source, OriginalExecutionTaskSource)
        or not isinstance(model, ActorExecutionScope)
    ):
        raise TypeError("Original claimed source/model/owner required")
    if (
        not isinstance(source.contexts, ClosedCategoryNavigationSourceContexts)
        or site_spec.configuration.site_id != "shopping"
        or site_spec.configuration.shopping_category_inputs is None
    ):
        raise OwnershipConflict(
            "Original closed Shopping category navigation source and site required"
        )

    def initial(
        evidence: EvidenceStore,
        spec: BrowserResourceSpec,
        intent: EvidenceRef,
        result: EvidenceRef,
    ) -> InitialObservationChecks:
        if not isinstance(
            spec.configuration.initialization, ShoppingCategoryInitialization
        ):
            raise OwnershipConflict(
                "Explicit original Shopping category navigation initialization required"
            )
        return CapturedCategoryNavigationInitialChecks(evidence, intent, result)

    def compose(
        d: TaskExecutionDeclarations,
        r: TaskExecutionResources,
        a: ExecutionTaskAuthorities,
        resources: OriginalTaskResourceOwner,
    ) -> CategoryNavigationTaskExecution:
        runtime = CategoryNavigationExecutionRuntime(
            source,
            owner.runs,
            owner.claims,
            OriginalExecutionTaskAuthority(resources),
            owner.evidence,
            controls,
            clock,
            owner.plans,
        )
        return shopping_category_task_execution(d, r, a, runtime)

    rights = CategoryNavigationClaimedSiteAuthority(owner, site_spec, site_acquisition)
    selected = owned_task_execution(
        declarations,
        owner,
        source,
        model,
        site_spec,
        site_acquisition,
        browser_declarations,
        journal=journal,
        bindings=bindings,
        controls=controls,
        clock=clock,
        trace_root=trace_root,
        calls_root=calls_root,
        trace_capacity=trace_capacity,
        policy=OwnedTaskPolicy(
            lambda owner, spec, operation: rights,
            rights,
            lambda evidence, spec, site: CategoryNavigationBrowserChecks(),
            initial,
            CategoryNavigationInitialComparison(owner.evidence),
        ),
        compose=compose,
    )
    return OwnedCategoryNavigationExecution(
        selected.bundle, selected.resources, selected.physical_site
    )
