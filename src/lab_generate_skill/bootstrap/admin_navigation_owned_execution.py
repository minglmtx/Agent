"""Admin codecs on the existing claimed-owner task assembly; no live defaults."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from .admin_navigation_claimed_authority import (
    AdminNavigationClaimedSiteAuthority,
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
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
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
from lab_generate_skill.sites.shopping_admin.tasks.navigation_equivalence import (
    NavigationInitialComparison,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_prepared_browser import (
    NavigationPreparedBrowserChecks,
)
from .admin_navigation_closed_source import ClosedAdminNavigationSourceContexts
from .admin_navigation_initial_capture import CapturedAdminNavigationInitialChecks
from .admin_navigation_task_execution import (
    admin_navigation_task_execution,
    AdminNavigationExecutionRuntime,
    AdminNavigationTaskExecution,
)
from .task_execution_bindings import (
    TaskExecutionDeclarations,
    TaskExecutionResources,
    ExecutionTaskAuthorities,
)
from .terminal_read_binding import owned_terminal_reads
from .owned_task_execution import (
    OwnedTaskExecution,
    OwnedTaskPolicy,
    TaskBrowserDeclarations,
    owned_task_execution,
)


@dataclass(frozen=True)
class OwnedAdminNavigationExecution(OwnedTaskExecution[AdminNavigationTaskExecution]):
    pass


def admin_navigation_owned_execution(
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
    metadata_cleanup_seconds: int | None = None,
) -> OwnedAdminNavigationExecution:
    if (
        not isinstance(declarations, TaskExecutionDeclarations)
        or not isinstance(site_spec, SiteResourceSpec)
        or not isinstance(owner, ClaimedRunResourceOwner)
        or not isinstance(source, OriginalExecutionTaskSource)
        or not isinstance(model, ActorExecutionScope)
    ):
        raise TypeError("Original claimed source/model/owner required")
    if (
        not isinstance(source.contexts, ClosedAdminNavigationSourceContexts)
        or site_spec.configuration.site_id != "shopping_admin"
        or site_spec.configuration.admin_navigation_inputs is None
    ):
        raise OwnershipConflict(
            "Original closed Admin navigation source and site required"
        )

    def initial(
        evidence: EvidenceStore,
        spec: BrowserResourceSpec,
        intent: EvidenceRef,
        result: EvidenceRef,
    ) -> InitialObservationChecks:
        if not isinstance(
            spec.configuration.initialization, AdminNavigationInitialization
        ):
            raise OwnershipConflict(
                "Explicit original Admin navigation initialization required"
            )
        return CapturedAdminNavigationInitialChecks(evidence, intent, result)

    def compose(
        d: TaskExecutionDeclarations,
        r: TaskExecutionResources,
        a: ExecutionTaskAuthorities,
        resources: OriginalTaskResourceOwner,
    ) -> AdminNavigationTaskExecution:
        runtime = AdminNavigationExecutionRuntime(
            source,
            owner.runs,
            owner.claims,
            OriginalExecutionTaskAuthority(resources),
            owner.evidence,
            controls,
            clock,
            owner.plans,
        )
        return admin_navigation_task_execution(
            d,
            r,
            a,
            runtime,
            initial_inputs=resources.inputs,
            capture_admission_handoff=True,
            terminal_reads=owned_terminal_reads(source, owner.evidence, d.plan),
        )

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
            AdminNavigationClaimedSiteAuthority,
            None,
            lambda evidence, spec, site: NavigationPreparedBrowserChecks(),
            initial,
            NavigationInitialComparison(owner.evidence),
            metadata_cleanup_seconds=metadata_cleanup_seconds,
        ),
        compose=compose,
    )
    return OwnedAdminNavigationExecution(
        selected.bundle, selected.resources, selected.physical_site
    )
