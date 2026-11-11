"""Default Map navigation task composition on the existing unified entry.

Already acquired batch site/model remain outside this per-attempt owner. Actual
source/claim/kernel/lease/acquisition/resume rights are mandatory supplied ports.
No old pytest driver, second runner/ledger, cached permit or replacement worker.
"""

from dataclasses import dataclass
from typing import Generic, TypeVar, overload
from lab_generate_skill.adapters.sites.resource import RegisteredSite
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.adapters.sites.task_capture import RecordedTaskCapture
from lab_generate_skill.adapters.sites.task_capture_admission_inputs import (
    TaskCaptureAdmissionInputs,
)
from lab_generate_skill.adapters.sites.task_terminal_inputs import (
    TaskTerminalEvidenceInputs,
)
from lab_generate_skill.ports.terminal_reads import TerminalEvidenceReads
from lab_generate_skill.adapters.sites.task_capture_initial_reads import (
    TaskCaptureInitialReads,
)
from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
)
from lab_generate_skill.adapters.sites.task_finalization import RecordedTaskFinalization
from lab_generate_skill.adapters.sites.task_native_authority import (
    OriginalTaskNativeAuthority,
)
from lab_generate_skill.sites.map.tasks.native_request_rules import (
    NavigationNativeRequestChecks,
)
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.adapters.sites.task_site_resume_authority import (
    OriginalTaskSiteResumeAuthority,
)
from lab_generate_skill.adapters.sites.task_site_capture_authority import (
    OriginalTaskSiteCaptureAuthority,
)
from lab_generate_skill.adapters.map_artifacts.origin_authority import (
    OriginalMapOriginAuthority,
)
from lab_generate_skill.application.task_preparation_admission import (
    TaskPreparationAuthority,
)
from lab_generate_skill.application.task_initialization_admission import (
    TaskInitializationAuthority,
)
from lab_generate_skill.application.task_capture_admission import TaskCaptureAuthority
from lab_generate_skill.application.task_finalization_admission import (
    TaskFinalizationAuthority,
)
from lab_generate_skill.domain.browser_capture import BrowserCaptureRequest
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_phase_source import TaskPhaseSourceState
from lab_generate_skill.application.construction_task_phase_source import (
    ConstructionTaskPhaseSources,
)
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from .task_initialization import DeferredTaskInitialization
from .task_candidate_inputs import InitializedTaskCandidateInputs
from .task_execution import RecordedConstructionTask
from .execution_task import RecordedExecutionTask
from .task_actor import CurrentTaskActorBinding
from lab_generate_skill.application.execution_task_actor_admission import (
    ExecutionTaskActorAdmissionDeps,
)
from lab_generate_skill.application.execution_task_phase_source import (
    ExecutionTaskPhaseSources,
    ExecutionTaskPhaseResources,
)
from lab_generate_skill.application.construction_task_phase_source import (
    ConstructionTaskPhaseResources,
)
from lab_generate_skill.ports.task_phase_source import (
    TaskPhaseSources,
    TaskPhaseResourceAuthority,
)
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.task_execution import InitializedTask
from .task_actor import TaskActorResources
from collections.abc import Callable
from .task_execution_composition import (
    TaskExecutionServices,
    TaskExecutionRuntime,
    ExecutionTaskRuntime,
    bind_task_execution,
)
from .map_task_execution_bindings import (
    MapTaskExecutionDeclarations,
    MapTaskExecutionResources,
    MapTaskExecutionAuthorities,
    MapExecutionTaskAuthorities,
    TaskInitialBinding,
)
from .map_task_preparation import map_task_preparation
from .map_task_initialization import map_navigation_task_initialization
from .map_task_capture import map_navigation_task_capture
from .map_task_finalization import map_task_finalization
from .task_capture_inputs import initialized_task_capture_inputs
from lab_generate_skill.adapters.map_artifacts.state_input_transport import (
    MapStateInputsTransport,
)


from .task_execution_bindings import (
    OriginalTaskInitialBinding as OriginalTaskInitialBinding,
)

TaskEntryT = TypeVar("TaskEntryT", RecordedConstructionTask, RecordedExecutionTask)


@dataclass(frozen=True)
class MapTaskExecution(Generic[TaskEntryT]):
    task: TaskEntryT
    preparation: RecordedSiteTaskPreparation
    initialization: DeferredTaskInitialization[RecordedTaskInitialization]
    capture: RecordedTaskCapture
    finalization: RecordedTaskFinalization
    native_authority: OriginalTaskNativeAuthority


@dataclass(frozen=True)
class MapExecutionTaskRuntime(ExecutionTaskRuntime):
    """The Map cleanup consumer also needs the actual controlled frozen-plan reader."""

    plans: RunPlans


@overload
def map_navigation_task_execution(
    declarations: MapTaskExecutionDeclarations,
    resources: MapTaskExecutionResources,
    authorities: MapTaskExecutionAuthorities,
    runtime: TaskExecutionRuntime,
    *,
    state_inputs: MapStateInputsTransport | None = None,
    initial_inputs: TaskInitializationInputs | None = None,
    terminal_reads: TerminalEvidenceReads | None = None,
    capture_admission_handoff: bool = False,
) -> MapTaskExecution[RecordedConstructionTask]: ...


@overload
def map_navigation_task_execution(
    declarations: MapTaskExecutionDeclarations,
    resources: MapTaskExecutionResources,
    authorities: MapExecutionTaskAuthorities,
    runtime: MapExecutionTaskRuntime,
    *,
    state_inputs: MapStateInputsTransport | None = None,
    initial_inputs: TaskInitializationInputs | None = None,
    terminal_reads: TerminalEvidenceReads | None = None,
    capture_admission_handoff: bool = False,
) -> MapTaskExecution[RecordedExecutionTask]: ...


def map_navigation_task_execution(
    declarations: MapTaskExecutionDeclarations,
    resources: MapTaskExecutionResources,
    authorities: MapTaskExecutionAuthorities,
    runtime: TaskExecutionRuntime | MapExecutionTaskRuntime,
    *,
    state_inputs: MapStateInputsTransport | None = None,
    initial_inputs: TaskInitializationInputs | None = None,
    terminal_reads: TerminalEvidenceReads | None = None,
    capture_admission_handoff: bool = False,
) -> (
    MapTaskExecution[RecordedConstructionTask] | MapTaskExecution[RecordedExecutionTask]
):
    if (
        not isinstance(declarations, MapTaskExecutionDeclarations)
        or not isinstance(resources, MapTaskExecutionResources)
        or not isinstance(authorities, MapTaskExecutionAuthorities)
        or not isinstance(runtime, (TaskExecutionRuntime, MapExecutionTaskRuntime))
    ):
        raise TypeError("Explicit original typed Map composition inputs required")
    if any(
        x is None
        for group in (declarations, resources, authorities, runtime)
        for x in vars(group).values()
    ):
        raise ValueError(
            "All original resources, authorities and declarations mandatory"
        )
    plan = TaskExecutionPlan.model_validate(declarations.plan)
    sources: TaskPhaseSources
    phase_resources: TaskPhaseResourceAuthority
    if isinstance(runtime, MapExecutionTaskRuntime):
        if (
            not isinstance(authorities, MapExecutionTaskAuthorities)
            or plan.intent.source_kind != "execution"
        ):
            raise OwnershipConflict(
                "Single Map runtime requires actual single Actor source authority"
            )
        execution_sources = ExecutionTaskPhaseSources(runtime.source_reader)
        sources = execution_sources
        phase_resources = ExecutionTaskPhaseResources(
            execution_sources, runtime.authority
        )
    else:
        if (
            isinstance(authorities, MapExecutionTaskAuthorities)
            or plan.intent.source_kind != "construction"
        ):
            raise OwnershipConflict(
                "Construction Map runtime cannot ignore single source fields"
            )
        construction_sources = ConstructionTaskPhaseSources(runtime.construction)
        sources = construction_sources
        phase_resources = ConstructionTaskPhaseResources(
            construction_sources, runtime.authority
        )
    if resources.site_spec.configuration.site_id != "map" or not isinstance(
        resources.site_spec.configuration.map_inputs, MapNavigationWorkerInputs
    ):
        raise ValueError("Explicit selected Map navigation resource required")
    if not isinstance(resources.native_source, TaskSiteAuthority):
        raise TypeError("Original registered task-site authority required")
    origin = resources.site_spec.configuration.map_inputs.origin
    if (
        origin.mode == "frozen_context"
        and origin.source_context_ref != plan.intent.public_context_ref
    ):
        raise OwnershipConflict(
            "Current task changed exact original source origin/context"
        )
    if origin.mode == "frozen_context":
        parent = resources.native_source.origin
        if (
            not isinstance(parent, OriginalMapOriginAuthority)
            or parent.source is None
            or parent.read_operation != plan.read_operation
        ):
            raise OwnershipConflict(
                "Map parent origin changed original construction source"
            )
        source_progress = TaskPhaseSourceState.model_validate(
            parent.source.verify_source(plan.read_operation)
        )
        progress = sources.read(
            plan, plan.read_operation, runtime.controls.bind(plan.read_operation)
        )
        if (
            source_progress != progress
            or source_progress.intent != plan.intent
            or progress.intent.binding.run != plan.intent.binding.run
            or progress.task.identity != plan.intent.binding.task
            or progress.public_context_ref != origin.source_context_ref
            or progress.context_receipt_ref != origin.source_context_receipt_ref
            or progress.intent != plan.intent
        ):
            raise OwnershipConflict(
                "Map parent origin changed original construction source"
            )
    if (
        declarations.preparation.scope != declarations.reset.scope
        or declarations.capture.scope != declarations.reset.scope
        or declarations.finalization.scope != declarations.reset.scope
    ):
        raise OwnershipConflict(
            "All original Map task phases require the same frozen scope"
        )
    native_authority: OriginalTaskNativeAuthority | None = None

    def bind_native(live: RegisteredSite) -> None:
        if native_authority is None:
            raise OwnershipConflict("Original native supplier has not been composed")
        resources.native_source.bind_native(native_authority, live.site)

    prep = map_task_preparation(
        plan,
        declarations.preparation,
        resources.site_spec,
        resources.site,
        resources.site_journal,
        runtime.evidence,
        runtime.controls,
        resources.bindings,
        TaskPreparationAuthority(
            sources, runtime.runs, phase_resources, runtime.evidence
        ),
        on_acquired=bind_native,
        state_inputs=state_inputs,
    )
    binding = OriginalTaskInitialBinding()

    def initialize(
        original_plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> RecordedTaskInitialization:
        selected = resources.initialization(prep, operation, control)
        if not isinstance(selected, TaskInitialBinding) or not selected.complete():
            raise TypeError("Original typed complete initial binding required")
        binding.value = selected
        if (
            selected.browser is not resources.browser()
            or selected.browser.journal is not resources.browser_journal
        ):
            raise OwnershipConflict(
                "Initial factory changed retained original browser owner/journal"
            )
        return map_navigation_task_initialization(
            original_plan,
            selected.declaration,
            selected.declaration_ref,
            selected.browser,
            prep.records,
            TaskInitializationAuthority(
                selected.declaration_ref,
                sources,
                runtime.runs,
                phase_resources,
                runtime.evidence,
            ),
            selected.state,
            selected.context,
            selected.capture,
            selected.initial,
            runtime.evidence,
            runtime.controls,
            inputs=selected.inputs,
            adoption_checks=selected.adoption_checks,
        )

    late = DeferredTaskInitialization(plan, initialize)
    capture_initials = (
        None
        if initial_inputs is None
        else TaskCaptureInitialReads(plan, initial_inputs, late.original)
    )

    terminal_inputs = None
    if terminal_reads is not None:
        if initial_inputs is None or capture_initials is None:
            raise ValueError(
                "Supervised terminal reading requires original owned initial inputs"
            )
        terminal_inputs = TaskTerminalEvidenceInputs(
            plan,
            initial_inputs,
            terminal_reads,
            capture_initials,
            lambda control: initialized_task_capture_inputs(
                prep, late.original(), control
            ).initial,
        )

    def browser() -> RetainedBrowserResource:
        value = resources.browser()
        if value is None:
            raise OwnershipConflict("Original acquired browser unavailable for capture")
        return value

    if type(capture_admission_handoff) is not bool:
        raise TypeError("Capture admission handoff requires an explicit bool")
    admission_evidence = runtime.evidence
    if capture_admission_handoff:
        if initial_inputs is None or capture_initials is None:
            raise ValueError("Capture admission requires original owned input handoff")
        admission_evidence = TaskCaptureAdmissionInputs(
            plan,
            declarations.capture,
            declarations.capture_ref,
            initial_inputs,
            prep,
            late.original,
            capture_initials,
            runtime.evidence,
        )

    capture, evaluator = map_navigation_task_capture(
        plan,
        declarations.capture,
        declarations.capture_ref,
        lambda control: initialized_task_capture_inputs(prep, late.original(), control),
        browser,
        resources.trace,
        resources.site,
        resources.site_spec,
        prep.records,
        TaskCaptureAuthority(
            declarations.capture_ref,
            sources,
            runtime.runs,
            phase_resources,
            resources.trace,
            admission_evidence,
        ),
        binding,
        OriginalTaskSiteCaptureAuthority(plan, prep, lambda: capture),
        runtime.evidence,
        runtime.controls,
        runtime.clock,
        initials=capture_initials,
        terminal_inputs=terminal_inputs,
    )
    finalization = map_task_finalization(
        plan,
        declarations.finalization,
        declarations.finalization_ref,
        declarations.reset,
        prep,
        resources.browser,
        resources.browser_journal,
        lambda: capture.state.closure_ref,
        TaskFinalizationAuthority(
            declarations.finalization_ref,
            sources,
            runtime.runs,
            runtime.claims,
            runtime.plans,
            authorities.finalization,
            runtime.evidence,
        ),
        authorities.unstarted,
        OriginalTaskSiteResumeAuthority(plan, lambda: finalization),
        runtime.evidence,
        runtime.controls,
        state_inputs=state_inputs,
    )
    services = TaskExecutionServices(
        prep,
        late,
        capture,
        evaluator,
        finalization,
        finalization.states,
        InitializedTaskCandidateInputs(late, runtime.evidence, runtime.controls),
    )
    scope = (
        resources.site.scope
        if isinstance(resources.site, RetainedSiteResource)
        else None
    )
    task: RecordedConstructionTask | RecordedExecutionTask
    if isinstance(runtime, MapExecutionTaskRuntime):
        if not isinstance(authorities, MapExecutionTaskAuthorities):
            raise OwnershipConflict(
                "Original single Map Actor source authority missing"
            )
        actor_sources = ExecutionTaskActorAdmissionDeps(
            runtime.source_reader,
            runtime.runs,
            runtime.claims,
            runtime.evidence,
            authorities.actor_source,
        )
        actors = CurrentTaskActorBinding(
            plan,
            actor_sources,
            resources.actor,
            runtime.evidence,
            runtime.controls,
            runtime.clock,
        )
        task = bind_task_execution(
            plan, services, runtime, actors, resource_scope=scope
        )
    else:
        task = bind_task_execution(
            plan, services, runtime, resources.actor, resource_scope=scope
        )
    if resources.native_source.spec != resources.site_spec:
        raise OwnershipConflict("Native source replaced original registered site")
    native_authority = OriginalTaskNativeAuthority(
        plan, prep, finalization, NavigationNativeRequestChecks()
    )
    if isinstance(resources.site, RetainedSiteResource):
        if (
            resources.site.spec != resources.site_spec
            or resources.site.journal is not resources.site_journal
            or resources.site.authority is not resources.native_source
            or resources.site.phase != "new"
        ):
            raise OwnershipConflict(
                "A fresh original site owner/source/journal is required"
            )
    elif isinstance(resources.site, RegisteredSite):
        bind_native(resources.site)
    else:
        raise TypeError("An original registered or retained site owner is required")
    if isinstance(task, RecordedConstructionTask):
        return MapTaskExecution(
            task, prep, late, capture, finalization, native_authority
        )
    return MapTaskExecution(task, prep, late, capture, finalization, native_authority)
