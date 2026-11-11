"""Compose the existing task entry and Actor binding; no dispatch or allow defaults."""

from lab_generate_skill.ports.construction_actor_admission import (
    ActorAdmissionAuthority,
)

from lab_generate_skill.ports.construction_task_execution import TaskExecutionAuthority

from contextlib import AbstractContextManager
from collections.abc import Callable
from dataclasses import dataclass
from typing import overload, cast
from lab_generate_skill.application.admit_candidate import CandidateAdmissionDeps
from lab_generate_skill.application.construction_task_deps import (
    ConstructionTaskExecutionDeps as TaskExecutionDeps,
)
from lab_generate_skill.application.task_actor_admission import TaskActorAdmissionDeps
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.ports.actor import ActorRunAuthority
from lab_generate_skill.ports.actor_admission import (
    CandidateInputs,
)
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.evaluator import Evaluator
from lab_generate_skill.ports.lifecycle import Clock, OperationControls
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.state_records import StateRecords
from lab_generate_skill.ports.task_execution import (
    TaskPreparation,
    TaskInitialization,
    TaskCapture,
    TaskFinalization,
)
from .task_actor import CurrentTaskActorBinding, TaskActorResources
from .task_execution import RecordedConstructionTask
from .execution_task import RecordedExecutionTask
from lab_generate_skill.application.execution_task_deps import (
    ExecutionTaskExecutionDeps,
)
from lab_generate_skill.ports.execution_task import (
    ExecutionTaskSources,
    ExecutionTaskAuthority,
)
from lab_generate_skill.ports.task_execution import TaskActorBinding
from lab_generate_skill.domain.errors import OwnershipConflict


@dataclass(frozen=True)
class TaskExecutionServices:
    preparation: TaskPreparation
    initialization: TaskInitialization
    capture: TaskCapture
    evaluator: Evaluator
    finalization: TaskFinalization
    states: StateRecords
    inputs: CandidateInputs


@dataclass(frozen=True)
class TaskExecutionRuntime:
    construction: ConstructionJournal
    runs: RunJournal
    claims: SourceClaims
    plans: RunPlans
    authority: TaskExecutionAuthority
    actor_admission: ActorAdmissionAuthority
    actor_source: ActorRunAuthority
    evidence: EvidenceStore
    controls: OperationControls
    clock: Clock


def _bind_construction_task_execution(
    plan: TaskExecutionPlan,
    services: TaskExecutionServices,
    runtime: TaskExecutionRuntime,
    actor_resources: Callable[
        [InitializedTask, PreparedActorInput], TaskActorResources
    ],
    *,
    resource_scope: Callable[[], AbstractContextManager[object]] | None = None,
) -> RecordedConstructionTask:
    plan = TaskExecutionPlan.model_validate(plan)
    if not isinstance(services, TaskExecutionServices) or not isinstance(
        runtime, TaskExecutionRuntime
    ):
        raise TypeError("Explicit original typed task services/runtime required")
    if any(
        x is None for x in (*vars(services).values(), *vars(runtime).values())
    ) or not callable(actor_resources):
        raise ValueError(
            "All original source/physical/Actor/claim dependencies mandatory"
        )
    admission = CandidateAdmissionDeps(
        runtime.construction,
        runtime.runs,
        services.inputs,
        runtime.actor_admission,
        runtime.controls,
        runtime.claims,
    )
    actor_admission = TaskActorAdmissionDeps(
        runtime.construction,
        runtime.runs,
        runtime.claims,
        runtime.plans,
        runtime.evidence,
        runtime.actor_source,
    )
    actors = CurrentTaskActorBinding(
        plan,
        actor_admission,
        actor_resources,
        runtime.evidence,
        runtime.controls,
        runtime.clock,
    )
    return RecordedConstructionTask(
        plan,
        TaskExecutionDeps(
            runtime.construction,
            runtime.runs,
            admission,
            services.preparation,
            services.initialization,
            actors,
            services.capture,
            services.evaluator,
            services.finalization,
            services.states,
            runtime.authority,
            runtime.evidence,
            runtime.controls,
            runtime.clock,
        ),
        resource_scope=resource_scope,
    )


@dataclass(frozen=True)
class ExecutionTaskRuntime:
    """All single-task source/runtime rights mandatory; no construction journal."""

    source_reader: ExecutionTaskSources
    runs: RunJournal
    claims: SourceClaims
    authority: ExecutionTaskAuthority
    evidence: EvidenceStore
    controls: OperationControls
    clock: Clock


@overload
def bind_task_execution(
    plan: TaskExecutionPlan,
    services: TaskExecutionServices,
    runtime: TaskExecutionRuntime,
    actor_resources: Callable[
        [InitializedTask, PreparedActorInput], TaskActorResources
    ],
    *,
    resource_scope: Callable[[], AbstractContextManager[object]] | None = None,
) -> RecordedConstructionTask: ...


@overload
def bind_task_execution(
    plan: TaskExecutionPlan,
    services: TaskExecutionServices,
    runtime: ExecutionTaskRuntime,
    actor_resources: TaskActorBinding,
    *,
    resource_scope: Callable[[], AbstractContextManager[object]] | None = None,
) -> RecordedExecutionTask: ...


def bind_task_execution(
    plan: TaskExecutionPlan,
    services: TaskExecutionServices,
    runtime: TaskExecutionRuntime | ExecutionTaskRuntime,
    actor_resources: (
        Callable[[InitializedTask, PreparedActorInput], TaskActorResources]
        | TaskActorBinding
    ),
    *,
    resource_scope: Callable[[], AbstractContextManager[object]] | None = None,
) -> RecordedConstructionTask | RecordedExecutionTask:
    """Choose one actual business admission/result adapter over one lifecycle.

    Construction's resource factory binds CurrentTaskActorBinding. Single tasks
    supply the existing Actor binding port with their actual source authority.
    Neither branch manufactures missing rights or a role/runner/ledger.
    """
    plan = TaskExecutionPlan.model_validate(plan)
    if not isinstance(services, TaskExecutionServices) or not isinstance(
        runtime, (TaskExecutionRuntime, ExecutionTaskRuntime)
    ):
        raise TypeError(
            "Explicit original typed services and business runtime required"
        )
    if any(v is None for v in (*vars(services).values(), *vars(runtime).values())):
        raise ValueError(
            "All original source/claim/resource/Actor dependencies required"
        )
    if isinstance(runtime, ExecutionTaskRuntime):
        if plan.intent.source_kind != "execution":
            raise OwnershipConflict("Single runtime cannot consume construction intent")
        if not callable(getattr(actor_resources, "bind", None)):
            raise TypeError(
                "Single task requires its actual existing Actor binding port"
            )
        actors = cast(TaskActorBinding, actor_resources)
        return RecordedExecutionTask(
            plan,
            ExecutionTaskExecutionDeps(
                runtime.source_reader,
                services.inputs,
                runtime.claims,
                runtime.runs,
                services.preparation,
                services.initialization,
                actors,
                services.capture,
                services.evaluator,
                services.finalization,
                services.states,
                runtime.authority,
                runtime.evidence,
                runtime.controls,
                runtime.clock,
            ),
            resource_scope=resource_scope,
        )
    if plan.intent.source_kind != "construction":
        raise OwnershipConflict("Construction runtime cannot consume execution intent")
    if not callable(actor_resources):
        raise TypeError("Construction requires original Actor resource factory")
    return _bind_construction_task_execution(
        plan, services, runtime, actor_resources, resource_scope=resource_scope
    )
