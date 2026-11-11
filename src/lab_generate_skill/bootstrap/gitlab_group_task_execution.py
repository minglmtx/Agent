"""Group on existing single/construction owners and the sole task lifecycle.

All current source, origin, claim, physical and cleanup authorities are supplied;
this composition starts nothing and cannot qualify an original task or source.
"""

from dataclasses import dataclass
from typing import Generic, TypeVar, overload
from urllib.parse import urlsplit
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
from lab_generate_skill.adapters.sites.task_capture import RecordedTaskCapture
from lab_generate_skill.adapters.sites.task_finalization import RecordedTaskFinalization
from lab_generate_skill.application.construction_task_phase_source import (
    ConstructionTaskPhaseSources,
    ConstructionTaskPhaseResources,
)
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
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.task_phase_source import (
    TaskPhaseSources,
    TaskPhaseResourceAuthority,
)
from lab_generate_skill.sites.gitlab.tasks.group_policy import group_initial_spec
from lab_generate_skill.sites.gitlab.tasks.group_spec import GroupSpec
from lab_generate_skill.sites.gitlab.tasks.group_native_request import (
    GroupNativeRequestChecks,
)
from lab_generate_skill.sites.gitlab.tasks.group_initial_capture import (
    group_initial_capture_request,
)
from .task_execution_bindings import (
    TaskExecutionDeclarations,
    TaskExecutionResources,
    TaskExecutionAuthorities,
    ExecutionTaskAuthorities,
    TaskInitialBinding,
    OriginalTaskInitialBinding,
)
from .task_execution_composition import (
    ExecutionTaskRuntime,
    TaskExecutionRuntime,
    TaskExecutionServices,
    bind_task_execution,
)
from .task_initialization import DeferredTaskInitialization
from .task_candidate_inputs import InitializedTaskCandidateInputs
from .task_actor import CurrentTaskActorBinding
from .execution_task import RecordedExecutionTask
from .task_execution import RecordedConstructionTask
from .task_capture_inputs import initialized_task_capture_inputs
from .gitlab_group_task_preparation import gitlab_group_task_preparation
from .gitlab_group_task_initialization import (
    gitlab_group_task_initialization,
    GroupTaskInitialization,
)
from .gitlab_group_task_capture import gitlab_group_task_capture
from .gitlab_group_task_finalization import gitlab_group_task_finalization

TaskEntryT = TypeVar("TaskEntryT", RecordedExecutionTask, RecordedConstructionTask)


@dataclass(frozen=True)
class GroupExecutionRuntime(ExecutionTaskRuntime):
    plans: RunPlans


@dataclass(frozen=True)
class GroupTaskExecution(Generic[TaskEntryT]):
    task: TaskEntryT
    preparation: RecordedSiteTaskPreparation
    initialization: DeferredTaskInitialization[GroupTaskInitialization]
    capture: RecordedTaskCapture
    finalization: RecordedTaskFinalization
    native_authority: OriginalTaskNativeAuthority


@overload
def gitlab_group_task_execution(
    declarations: TaskExecutionDeclarations,
    resources: TaskExecutionResources,
    authorities: ExecutionTaskAuthorities,
    runtime: GroupExecutionRuntime,
) -> GroupTaskExecution[RecordedExecutionTask]: ...


@overload
def gitlab_group_task_execution(
    declarations: TaskExecutionDeclarations,
    resources: TaskExecutionResources,
    authorities: TaskExecutionAuthorities,
    runtime: TaskExecutionRuntime,
) -> GroupTaskExecution[RecordedConstructionTask]: ...


def gitlab_group_task_execution(
    declarations: TaskExecutionDeclarations,
    resources: TaskExecutionResources,
    authorities: TaskExecutionAuthorities,
    runtime: GroupExecutionRuntime | TaskExecutionRuntime,
) -> (
    GroupTaskExecution[RecordedExecutionTask]
    | GroupTaskExecution[RecordedConstructionTask]
):
    if (
        not isinstance(declarations, TaskExecutionDeclarations)
        or not isinstance(resources, TaskExecutionResources)
        or not isinstance(authorities, TaskExecutionAuthorities)
        or not isinstance(runtime, (GroupExecutionRuntime, TaskExecutionRuntime))
    ):
        raise TypeError("Original typed Group task composition required")
    if any(
        value is None
        for group in (declarations, resources, authorities, runtime)
        for value in vars(group).values()
    ):
        raise ValueError("Every original Group resource and authority mandatory")
    plan = TaskExecutionPlan.model_validate(declarations.plan)
    scope = declarations.reset.scope
    group_initial_spec(scope.task)
    cfg = resources.site_spec.configuration
    if (
        cfg.site_id != "gitlab"
        or cfg.private_evidence is None
        or cfg.private_evidence.profile != GITLAB_GROUP_PRIVATE_JSON
        or any(
            value.scope != scope
            for value in (
                declarations.preparation,
                declarations.capture,
                declarations.finalization,
            )
        )
        or not isinstance(resources.native_source, TaskSiteAuthority)
        or resources.native_source.spec != resources.site_spec
        or resources.native_source.origin is None
    ):
        raise OwnershipConflict(
            "Original Group task phases, native profile and explicit origin authority required"
        )
    sources: TaskPhaseSources
    rights: TaskPhaseResourceAuthority
    if isinstance(runtime, GroupExecutionRuntime):
        if plan.intent.source_kind != "execution" or not isinstance(
            authorities, ExecutionTaskAuthorities
        ):
            raise OwnershipConflict(
                "Group single execution requires original single-task source rights"
            )
        single = ExecutionTaskPhaseSources(runtime.source_reader)
        sources, rights = single, ExecutionTaskPhaseResources(single, runtime.authority)
    else:
        if plan.intent.source_kind != "construction" or isinstance(
            authorities, ExecutionTaskAuthorities
        ):
            raise OwnershipConflict(
                "Group construction cannot ignore single-task source fields"
            )
        construction = ConstructionTaskPhaseSources(runtime.construction)
        sources, rights = construction, ConstructionTaskPhaseResources(
            construction, runtime.authority
        )
    control = runtime.controls.bind(plan.read_operation)
    progress = sources.read(plan, plan.read_operation, control)
    if progress.intent != plan.intent or progress.task.identity != scope.task:
        raise OwnershipConflict("Group composition changed original admitted task")
    reads = StateReads(runtime.evidence)
    public = reads.parse(
        progress.public_context_ref,
        "public-construction-context/1",
        PublicConstructionContext,
        control,
        visibility="public",
    )
    private = reads.parse(
        progress.task.private_spec_ref, "gitlab-group-creation/1", GroupSpec, control
    )
    origin = urlsplit(public.task.start_url)
    if (
        public.task.identity != scope.task
        or private.task != scope.task
        or origin.scheme != "http"
        or origin.hostname != "127.0.0.1"
        or origin.port is None
        or not 1024 <= origin.port <= 65535
    ):
        raise OwnershipConflict(
            "Original Group public/private loopback source required"
        )
    endpoint = "http://127.0.0.1:" + str(origin.port) + "/"
    native: OriginalTaskNativeAuthority | None = None

    def acquired(live: RegisteredSite) -> None:
        if native is None or live.site.instance.endpoint != endpoint:
            raise OwnershipConflict(
                "Group candidate must retain exact original measured public origin"
            )
        resources.native_source.bind_native(native, live.site)

    prep = gitlab_group_task_preparation(
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
    ) -> GroupTaskInitialization:
        selected = resources.initialization(prep, operation, control)
        if not isinstance(selected, TaskInitialBinding) or not selected.complete():
            raise TypeError("Original complete Group initial binding required")
        if (
            selected.browser is not resources.browser()
            or selected.browser.journal is not resources.browser_journal
        ):
            raise OwnershipConflict(
                "Group initial binding changed retained original browser"
            )
        prepared = prep.state.prepare_request
        if prepared is None:
            raise OwnershipConflict("Original Group prepare result required")
        before = group_initial_capture_request(selected.declaration, prepared)
        if before.operation.operation_id in (
            declarations.capture.page_operation_id,
            declarations.capture.guard_operation_id,
            declarations.capture.close_operation_id,
        ):
            raise OwnershipConflict(
                "Group before/terminal/guard operations must differ"
            )
        held.value = selected
        return gitlab_group_task_initialization(
            original,
            selected.declaration,
            selected.declaration_ref,
            selected.browser,
            prep,
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
        )

    late = DeferredTaskInitialization(plan, initialize)

    def browser() -> RetainedBrowserResource:
        value = resources.browser()
        if value is None:
            raise OwnershipConflict("Original Group retained browser unavailable")
        return value

    capture, evaluator = gitlab_group_task_capture(
        plan,
        declarations.capture,
        declarations.capture_ref,
        lambda control: initialized_task_capture_inputs(prep, late.original(), control),
        browser,
        resources.trace,
        resources.site,
        resources.site_spec,
        prep.records,
        late.original,
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
    final = gitlab_group_task_finalization(
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
    resource_scope = (
        resources.site.scope
        if isinstance(resources.site, RetainedSiteResource)
        else None
    )
    task: RecordedExecutionTask | RecordedConstructionTask
    if isinstance(runtime, GroupExecutionRuntime):
        assert isinstance(authorities, ExecutionTaskAuthorities)
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
            plan, services, runtime, actors, resource_scope=resource_scope
        )
    else:
        task = bind_task_execution(
            plan, services, runtime, resources.actor, resource_scope=resource_scope
        )
    native = OriginalTaskNativeAuthority(plan, prep, final, GroupNativeRequestChecks())
    if isinstance(resources.site, RetainedSiteResource):
        if (
            resources.site.spec != resources.site_spec
            or resources.site.journal is not resources.site_journal
            or resources.site.authority is not resources.native_source
            or resources.site.phase != "new"
        ):
            raise OwnershipConflict("Fresh original Group site owner/source required")
    elif isinstance(resources.site, RegisteredSite):
        acquired(resources.site)
    else:
        raise TypeError("Original retained/registered Group site required")
    if isinstance(task, RecordedExecutionTask):
        return GroupTaskExecution(task, prep, late, capture, final, native)
    return GroupTaskExecution(task, prep, late, capture, final, native)
