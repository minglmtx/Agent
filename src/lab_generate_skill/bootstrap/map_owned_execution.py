"""Original Map business policy on shared actual-owner assembly; no lifecycle fork."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.map_artifacts.state_input_transport import (
    MapStateInputsTransport,
)
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.sites.claimed_authority import (
    ClaimedSiteResourceAuthority,
)
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.adapters.map_artifacts.origin_authority import (
    OriginalMapOriginAuthority,
)
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_resource_owner import (
    OriginalTaskResourceOwner,
)
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.trace_plan import TraceCapacity
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControls,
    OperationControl,
    ResourceJournal,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.ports.task_bindings import TaskBindings
from lab_generate_skill.application.execution_task_phase_source import (
    ExecutionTaskOriginSource,
    ExecutionTaskPhaseSources,
)
from lab_generate_skill.adapters.sites.execution_task_authority import (
    OriginalExecutionTaskAuthority,
)
from lab_generate_skill.sites.map.tasks.navigation_equivalence import (
    NavigationInitialComparison,
)
from lab_generate_skill.sites.map.tasks.navigation_initial_observation import (
    NavigationInitialObservationChecks,
)
from .map_closed_source import ClosedMapSourceContexts
from .map_overlay_records import map_prepared_browser_checks
from .map_task_execution import (
    map_navigation_task_execution,
    MapTaskExecution,
    MapExecutionTaskRuntime,
)
from .execution_task import RecordedExecutionTask
from .task_execution_bindings import (
    TaskExecutionDeclarations,
    TaskExecutionResources,
    ExecutionTaskAuthorities,
)
from .terminal_read_binding import owned_terminal_reads
from .owned_task_execution import (
    OwnedTaskExecution,
    OwnedTaskPolicy,
    owned_task_execution,
    TaskBrowserDeclarations as TaskBrowserDeclarations,
)

__all__ = [
    "TaskBrowserDeclarations",
    "OwnedMapExecution",
    "map_navigation_owned_execution",
]


@dataclass(frozen=True)
class OwnedMapExecution(OwnedTaskExecution[MapTaskExecution[RecordedExecutionTask]]):
    pass


MapTaskExecutionDeclarations = TaskExecutionDeclarations


def map_navigation_owned_execution(
    declarations: MapTaskExecutionDeclarations,
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
    state_inputs: MapStateInputsTransport | None = None,
) -> OwnedMapExecution:
    if (
        not isinstance(declarations, TaskExecutionDeclarations)
        or not isinstance(site_spec, SiteResourceSpec)
        or not isinstance(owner, ClaimedRunResourceOwner)
        or not isinstance(source, OriginalExecutionTaskSource)
        or not isinstance(model, ActorExecutionScope)
    ):
        raise TypeError("Typed original source/claim/model required")
    if (
        not isinstance(source.contexts, ClosedMapSourceContexts)
        or not isinstance(owner.sources, ExecutionTaskPhaseSources)
        or site_spec.configuration.site_id != "map"
    ):
        raise OwnershipConflict("Original Map closed source and site required")
    if state_inputs is not None and (
        not isinstance(state_inputs, MapStateInputsTransport)
        or state_inputs.task != declarations.plan.intent.binding.task
    ):
        raise OwnershipConflict("Map state input transport changed original task")
    origin = OriginalMapOriginAuthority(
        contexts=source.contexts,
        evidence=owner.evidence,
        source=ExecutionTaskOriginSource(declarations.plan, owner.sources, controls),
        read_operation=declarations.plan.read_operation,
    )

    def initial(
        evidence: EvidenceStore,
        spec: BrowserResourceSpec,
        intent: EvidenceRef,
        result: EvidenceRef,
    ) -> InitialObservationChecks:
        selected = spec.configuration.initialization
        if not isinstance(selected, MapNavigationInitialization):
            raise OwnershipConflict(
                "Original selected navigation initialization required"
            )
        return NavigationInitialObservationChecks(
            evidence, MapInitialEvidence(intent_ref=intent, result_ref=result), selected
        )

    def compose(
        d: TaskExecutionDeclarations,
        r: TaskExecutionResources,
        a: ExecutionTaskAuthorities,
        resources: OriginalTaskResourceOwner,
    ) -> MapTaskExecution[RecordedExecutionTask]:
        runtime = MapExecutionTaskRuntime(
            source,
            owner.runs,
            owner.claims,
            OriginalExecutionTaskAuthority(resources),
            owner.evidence,
            controls,
            clock,
            owner.plans,
        )
        return map_navigation_task_execution(
            d,
            r,
            a,
            runtime,
            state_inputs=state_inputs,
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
            ClaimedSiteResourceAuthority,
            origin,
            lambda evidence, spec, site: map_prepared_browser_checks(
                evidence, spec.configuration, site.instance
            ),
            initial,
            NavigationInitialComparison(),
            metadata_cleanup_seconds=metadata_cleanup_seconds,
        ),
        compose=compose,
    )
    return OwnedMapExecution(
        selected.bundle, selected.resources, selected.physical_site
    )
