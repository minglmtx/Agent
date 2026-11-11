"""Group codecs on the existing claimed-owner task assembly; no live defaults."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from .gitlab_group_claimed_authority import (
    GroupClaimedSiteAuthority,
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
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
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
from lab_generate_skill.sites.gitlab.tasks.group_equivalence import (
    GroupInitialComparison,
)
from lab_generate_skill.sites.gitlab.tasks.group_reads import GroupStateReads
from .gitlab_group_capture import load_group_capture
from lab_generate_skill.sites.gitlab.tasks.group_browser_binding import (
    GroupBrowserChecks,
)
from .gitlab_group_closed_source import ClosedGroupSourceContexts
from lab_generate_skill.sites.gitlab.tasks.group_source_initial import (
    CapturedGroupInitialChecks,
)
from .gitlab_group_task_execution import (
    gitlab_group_task_execution,
    GroupExecutionRuntime,
    GroupTaskExecution,
)
from .task_execution_bindings import (
    TaskExecutionDeclarations,
    TaskExecutionResources,
    ExecutionTaskAuthorities,
)
from .execution_task import RecordedExecutionTask
from .owned_task_execution import (
    OwnedTaskExecution,
    OwnedTaskPolicy,
    TaskBrowserDeclarations,
    owned_task_execution,
)


@dataclass(frozen=True)
class OwnedGroupExecution(
    OwnedTaskExecution[GroupTaskExecution[RecordedExecutionTask]]
):
    pass


def gitlab_group_owned_execution(
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
) -> OwnedGroupExecution:
    if (
        not isinstance(declarations, TaskExecutionDeclarations)
        or not isinstance(site_spec, SiteResourceSpec)
        or not isinstance(owner, ClaimedRunResourceOwner)
        or not isinstance(source, OriginalExecutionTaskSource)
        or not isinstance(model, ActorExecutionScope)
    ):
        raise TypeError("Original claimed source/model/owner required")
    if (
        not isinstance(source.contexts, ClosedGroupSourceContexts)
        or site_spec.configuration.site_id != "gitlab"
        or site_spec.configuration.gitlab_group_inputs is None
    ):
        raise OwnershipConflict("Original closed Group source and site required")

    def initial(
        evidence: EvidenceStore,
        spec: BrowserResourceSpec,
        intent: EvidenceRef,
        result: EvidenceRef,
    ) -> InitialObservationChecks:
        if not isinstance(spec.configuration.initialization, GitlabGroupInitialization):
            raise OwnershipConflict("Explicit original Group initialization required")
        return CapturedGroupInitialChecks(evidence, intent, result)

    def compose(
        d: TaskExecutionDeclarations,
        r: TaskExecutionResources,
        a: ExecutionTaskAuthorities,
        resources: OriginalTaskResourceOwner,
    ) -> GroupTaskExecution[RecordedExecutionTask]:
        runtime = GroupExecutionRuntime(
            source,
            owner.runs,
            owner.claims,
            OriginalExecutionTaskAuthority(resources),
            owner.evidence,
            controls,
            clock,
            owner.plans,
        )
        return gitlab_group_task_execution(d, r, a, runtime)

    rights = GroupClaimedSiteAuthority(owner, site_spec, site_acquisition)
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
            lambda evidence, spec, site: GroupBrowserChecks(
                evidence, load_group_capture
            ),
            initial,
            GroupInitialComparison(GroupStateReads(owner.evidence, load_group_capture)),
        ),
        compose=compose,
    )
    return OwnedGroupExecution(
        selected.bundle, selected.resources, selected.physical_site
    )
