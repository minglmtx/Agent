"""Shopping category navigation on the original single-task lifecycle and mandatory owners.

Only site codecs and declared collectors differ. Source, claim, current phase,
Actor admission, once state and cleanup use the existing neutral consumers.
Composition grants no source or resource permission and performs no acquisition.
"""

from dataclasses import dataclass
import hashlib
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.sites.resource import RegisteredSite
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.adapters.sites.task_native_authority import (
    OriginalTaskNativeAuthority,
)
from lab_generate_skill.adapters.sites.task_site_capture_authority import (
    OriginalTaskSiteCaptureAuthority,
)
from lab_generate_skill.adapters.sites.task_site_resume_authority import (
    OriginalTaskSiteResumeAuthority,
)
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.adapters.sites.task_capture import RecordedTaskCapture
from lab_generate_skill.adapters.sites.task_finalization import RecordedTaskFinalization
from lab_generate_skill.application.execution_task_phase_source import (
    ExecutionTaskPhaseSources,
    ExecutionTaskPhaseResources,
)
from lab_generate_skill.application.execution_task_actor_admission import (
    ExecutionTaskActorAdmissionDeps,
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
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.policies.evidence_bytes import require_complete_read_bound
from lab_generate_skill.sites.shopping.tasks.navigation_spec import (
    CategoryNavigationSpec,
)
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationExecutionInput,
)
from lab_generate_skill.sites.shopping.tasks.navigation_native_request import (
    CategoryNavigationNativeRequestChecks,
)
from lab_generate_skill.sites.shopping.tasks.navigation_equivalence import (
    CategoryNavigationInitialComparison,
)
from .task_execution_bindings import (
    TaskExecutionDeclarations,
    TaskExecutionResources,
    ExecutionTaskAuthorities,
    TaskInitialBinding,
    OriginalTaskInitialBinding,
)
from .task_execution_composition import (
    ExecutionTaskRuntime,
    TaskExecutionServices,
    bind_task_execution,
)
from .task_initialization import DeferredTaskInitialization
from .task_candidate_inputs import InitializedTaskCandidateInputs
from .task_actor import CurrentTaskActorBinding
from .execution_task import RecordedExecutionTask
from .task_capture_inputs import initialized_task_capture_inputs
from .shopping_category_task_preparation import shopping_category_task_preparation
from .shopping_category_task_initialization import shopping_category_task_initialization
from .shopping_category_task_capture import shopping_category_task_capture
from .shopping_category_task_finalization import shopping_category_task_finalization


@dataclass(frozen=True)
class CategoryNavigationExecutionRuntime(ExecutionTaskRuntime):
    plans: RunPlans


@dataclass(frozen=True)
class CategoryNavigationTaskExecution:
    task: RecordedExecutionTask
    preparation: RecordedSiteTaskPreparation
    initialization: DeferredTaskInitialization[RecordedTaskInitialization]
    capture: RecordedTaskCapture
    finalization: RecordedTaskFinalization
    native_authority: OriginalTaskNativeAuthority


def shopping_category_task_execution(
    declarations: TaskExecutionDeclarations,
    resources: TaskExecutionResources,
    authorities: ExecutionTaskAuthorities,
    runtime: CategoryNavigationExecutionRuntime,
) -> CategoryNavigationTaskExecution:
    if (
        not isinstance(declarations, TaskExecutionDeclarations)
        or not isinstance(resources, TaskExecutionResources)
        or not isinstance(authorities, ExecutionTaskAuthorities)
        or not isinstance(runtime, CategoryNavigationExecutionRuntime)
    ):
        raise TypeError(
            "Explicit typed original Shopping category single-task composition required"
        )
    if any(
        x is None
        for group in (declarations, resources, authorities, runtime)
        for x in vars(group).values()
    ):
        raise ValueError("Every original resource and permission is mandatory")
    plan = TaskExecutionPlan.model_validate(declarations.plan)
    scope = declarations.reset.scope
    inputs = resources.site_spec.configuration.shopping_category_inputs
    if (
        plan.intent.source_kind != "execution"
        or resources.site_spec.configuration.site_id != "shopping"
        or resources.site_spec.configuration.schema_version
        != "site-worker-configuration/9"
        or inputs is None
        or inputs.scope != scope
        or any(
            d.scope != scope
            for d in (
                declarations.preparation,
                declarations.capture,
                declarations.finalization,
            )
        )
        or not isinstance(resources.native_source, TaskSiteAuthority)
        or resources.native_source.spec != resources.site_spec
    ):
        raise OwnershipConflict(
            "Original version9 Shopping category navigation phases/source required"
        )
    sources = ExecutionTaskPhaseSources(runtime.source_reader)
    rights = ExecutionTaskPhaseResources(sources, runtime.authority)
    control = runtime.controls.bind(plan.read_operation)
    progress = sources.read(plan, plan.read_operation, control)
    if progress.intent != plan.intent or progress.task.identity != scope.task:
        raise OwnershipConflict(
            "Shopping category composition changed original admitted source"
        )
    reads = StateReads(runtime.evidence)
    require_complete_read_bound(progress.public_context_ref, 2 * 1024**2)
    public = reads.parse(
        progress.public_context_ref,
        "public-construction-context/1",
        PublicConstructionContext,
        control,
        visibility="public",
    )
    require_complete_read_bound(progress.task.private_spec_ref, 2 * 1024**2)
    private = reads.parse(
        progress.task.private_spec_ref,
        "shopping-category-navigation/1",
        CategoryNavigationSpec,
        control,
    )
    if (
        progress.public_context_ref != plan.intent.public_context_ref
        or public.task.identity != scope.task
        or private.task != scope.task
        or public.task.start_url
        != inputs.origin.endpoint.rstrip("/") + private.original.start_path
        or inputs.native_contract_sha256 != private.native_contract_ref.sha256
        or inputs.private_input_sha256
        != hashlib.sha256(
            CategoryNavigationExecutionInput(spec=private).model_dump_json().encode()
        ).hexdigest()
    ):
        raise OwnershipConflict(
            "Shopping category resource changed original measured origin/input"
        )
    native: OriginalTaskNativeAuthority | None = None

    def acquired(live: RegisteredSite) -> None:
        if native is None:
            raise OwnershipConflict(
                "Original Shopping category native supplier is not composed"
            )
        resources.native_source.bind_native(native, live.site)

    prep = shopping_category_task_preparation(
        plan,
        declarations.preparation,
        resources.site_spec,
        resources.site,
        resources.site_journal,
        runtime.evidence,
        runtime.controls,
        resources.bindings,
        TaskPreparationAuthority(sources, runtime.runs, rights, runtime.evidence),
        on_acquired=acquired,
    )
    held = OriginalTaskInitialBinding()

    def initialize(
        original: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> RecordedTaskInitialization:
        selected = resources.initialization(prep, operation, control)
        if not isinstance(selected, TaskInitialBinding) or any(
            x is None for x in vars(selected).values()
        ):
            raise TypeError(
                "Original complete Shopping category initial binding required"
            )
        held.value = selected
        if (
            selected.browser is not resources.browser()
            or selected.browser.journal is not resources.browser_journal
        ):
            raise OwnershipConflict(
                "Shopping category initialization changed original browser owner"
            )
        return shopping_category_task_initialization(
            original,
            selected.declaration,
            selected.declaration_ref,
            selected.browser,
            prep.records,
            TaskInitializationAuthority(
                selected.declaration_ref,
                sources,
                runtime.runs,
                rights,
                runtime.evidence,
            ),
            selected.state,
            selected.context,
            selected.capture,
            selected.initial,
            CategoryNavigationInitialComparison(runtime.evidence),
            runtime.evidence,
            runtime.controls,
            inputs=selected.inputs,
        )

    late = DeferredTaskInitialization(plan, initialize)

    def browser() -> RetainedBrowserResource:
        value = resources.browser()
        if value is None:
            raise OwnershipConflict(
                "Original acquired Shopping category browser unavailable"
            )
        return value

    capture, evaluator = shopping_category_task_capture(
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
            rights,
            resources.trace,
            runtime.evidence,
        ),
        held,
        OriginalTaskSiteCaptureAuthority(plan, prep, lambda: capture),
        runtime.evidence,
        runtime.controls,
        runtime.clock,
    )
    final = shopping_category_task_finalization(
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
        OriginalTaskSiteResumeAuthority(plan, lambda: final),
        runtime.evidence,
        runtime.controls,
    )
    services = TaskExecutionServices(
        prep,
        late,
        capture,
        evaluator,
        final,
        final.states,
        InitializedTaskCandidateInputs(late, runtime.evidence, runtime.controls),
    )
    actors = CurrentTaskActorBinding(
        plan,
        ExecutionTaskActorAdmissionDeps(
            runtime.source_reader,
            runtime.runs,
            runtime.claims,
            runtime.evidence,
            authorities.actor_source,
        ),
        resources.actor,
        runtime.evidence,
        runtime.controls,
        runtime.clock,
    )
    task = bind_task_execution(
        plan,
        services,
        runtime,
        actors,
        resource_scope=(
            resources.site.scope
            if isinstance(resources.site, RetainedSiteResource)
            else None
        ),
    )
    native = OriginalTaskNativeAuthority(
        plan, prep, final, CategoryNavigationNativeRequestChecks()
    )
    if isinstance(resources.site, RetainedSiteResource):
        if (
            resources.site.spec != resources.site_spec
            or resources.site.journal is not resources.site_journal
            or resources.site.authority is not resources.native_source
            or resources.site.phase != "new"
        ):
            raise OwnershipConflict(
                "A fresh original Shopping category site owner is required"
            )
    elif isinstance(resources.site, RegisteredSite):
        acquired(resources.site)
    else:
        raise TypeError(
            "An original retained/registered Shopping category site owner is required"
        )
    return CategoryNavigationTaskExecution(task, prep, late, capture, final, native)
