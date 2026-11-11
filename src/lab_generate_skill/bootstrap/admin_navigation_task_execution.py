"""Admin navigation on the original single-task lifecycle and mandatory owners.

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
from lab_generate_skill.sites.shopping_admin.tasks.navigation_spec import (
    AdminNavigationSpec,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationExecutionInput,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_native_request import (
    NavigationNativeRequestChecks,
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
from .admin_navigation_task_preparation import admin_navigation_task_preparation
from .admin_navigation_task_initialization import admin_navigation_task_initialization
from .admin_navigation_task_capture import admin_navigation_task_capture
from .admin_navigation_task_finalization import admin_navigation_task_finalization


@dataclass(frozen=True)
class AdminNavigationExecutionRuntime(ExecutionTaskRuntime):
    plans: RunPlans


@dataclass(frozen=True)
class AdminNavigationTaskExecution:
    task: RecordedExecutionTask
    preparation: RecordedSiteTaskPreparation
    initialization: DeferredTaskInitialization[RecordedTaskInitialization]
    capture: RecordedTaskCapture
    finalization: RecordedTaskFinalization
    native_authority: OriginalTaskNativeAuthority


def admin_navigation_task_execution(
    declarations: TaskExecutionDeclarations,
    resources: TaskExecutionResources,
    authorities: ExecutionTaskAuthorities,
    runtime: AdminNavigationExecutionRuntime,
    *,
    initial_inputs: TaskInitializationInputs | None = None,
    terminal_reads: TerminalEvidenceReads | None = None,
    capture_admission_handoff: bool = False,
) -> AdminNavigationTaskExecution:
    if (
        not isinstance(declarations, TaskExecutionDeclarations)
        or not isinstance(resources, TaskExecutionResources)
        or not isinstance(authorities, ExecutionTaskAuthorities)
        or not isinstance(runtime, AdminNavigationExecutionRuntime)
    ):
        raise TypeError(
            "Explicit typed original Admin single-task composition required"
        )
    if any(
        x is None
        for group in (declarations, resources, authorities, runtime)
        for x in vars(group).values()
    ):
        raise ValueError("Every original resource and permission is mandatory")
    plan = TaskExecutionPlan.model_validate(declarations.plan)
    scope = declarations.reset.scope
    inputs = resources.site_spec.configuration.admin_navigation_inputs
    if (
        plan.intent.source_kind != "execution"
        or resources.site_spec.configuration.site_id != "shopping_admin"
        or resources.site_spec.configuration.schema_version
        != "site-worker-configuration/7"
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
            "Original version7 Admin navigation phases/source required"
        )
    sources = ExecutionTaskPhaseSources(runtime.source_reader)
    rights = ExecutionTaskPhaseResources(sources, runtime.authority)
    control = runtime.controls.bind(plan.read_operation)
    progress = sources.read(plan, plan.read_operation, control)
    if progress.intent != plan.intent or progress.task.identity != scope.task:
        raise OwnershipConflict("Admin composition changed original admitted source")
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
        "shopping-admin-page-navigation/1",
        AdminNavigationSpec,
        control,
    )
    if (
        progress.public_context_ref != plan.intent.public_context_ref
        or public.task.identity != scope.task
        or private.task != scope.task
        or public.task.start_url != inputs.origin.endpoint + private.start_path
        or inputs.native_contract_sha256 != private.native_contract_ref.sha256
        or inputs.private_input_sha256
        != hashlib.sha256(
            NavigationExecutionInput(spec=private).model_dump_json().encode()
        ).hexdigest()
    ):
        raise OwnershipConflict("Admin resource changed original measured origin/input")
    native: OriginalTaskNativeAuthority | None = None

    def acquired(live: RegisteredSite) -> None:
        if native is None:
            raise OwnershipConflict("Original Admin native supplier is not composed")
        resources.native_source.bind_native(native, live.site)

    prep = admin_navigation_task_preparation(
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
        if not isinstance(selected, TaskInitialBinding) or not selected.complete():
            raise TypeError("Original complete Admin initial binding required")
        held.value = selected
        if (
            selected.browser is not resources.browser()
            or selected.browser.journal is not resources.browser_journal
        ):
            raise OwnershipConflict(
                "Admin initialization changed original browser owner"
            )
        return admin_navigation_task_initialization(
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
            raise OwnershipConflict("Original acquired Admin browser unavailable")
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

    capture, evaluator = admin_navigation_task_capture(
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
            admission_evidence,
        ),
        held,
        OriginalTaskSiteCaptureAuthority(plan, prep, lambda: capture),
        runtime.evidence,
        runtime.controls,
        runtime.clock,
        initials=capture_initials,
        terminal_inputs=terminal_inputs,
    )
    final = admin_navigation_task_finalization(
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
        plan, prep, final, NavigationNativeRequestChecks()
    )
    if isinstance(resources.site, RetainedSiteResource):
        if (
            resources.site.spec != resources.site_spec
            or resources.site.journal is not resources.site_journal
            or resources.site.authority is not resources.native_source
            or resources.site.phase != "new"
        ):
            raise OwnershipConflict("A fresh original Admin site owner is required")
    elif isinstance(resources.site, RegisteredSite):
        acquired(resources.site)
    else:
        raise TypeError("An original retained/registered Admin site owner is required")
    return AdminNavigationTaskExecution(task, prep, late, capture, final, native)
