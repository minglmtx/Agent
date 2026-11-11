"""Real actor-only source plus shared preparation/cleanup gates; fake resource rights."""

from dataclasses import dataclass, replace
from pathlib import Path
from lab_generate_skill.application.execution_task_phase_source import (
    ExecutionTaskPhaseSources,
    ExecutionTaskPhaseResources,
)
from lab_generate_skill.application.task_preparation_admission import (
    TaskPreparationAuthority,
)
from lab_generate_skill.application.task_finalization_admission import (
    TaskFinalizationAuthority,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    ClosedTaskResources,
)
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from construction_storage_fixtures import put
from execution_task_fixtures import execution_case, ExecutionCase
from task_preparation_declaration_fixtures import preparation_declaration
from task_cleanup_admission_fixtures import UnitCleanupSource


@dataclass
class SinglePhaseCase:
    task: ExecutionCase
    sources: ExecutionTaskPhaseSources
    resources: ExecutionTaskPhaseResources
    preparation: TaskPreparationAuthority
    finalization: TaskFinalizationAuthority
    cleanup_source: UnitCleanupSource


def phase_case(root: Path) -> SinglePhaseCase:
    c = execution_case(root)
    store = c.source.data.store
    reset = c.phases.closed.reset_plan
    declaration = preparation_declaration(c.plan, reset, c.source.source.task, store)
    c.plan = c.plan.model_copy(
        update={"declaration_ref": put(store, declaration, declaration.schema_version)}
    )
    sources = ExecutionTaskPhaseSources(c.deps.source_reader)
    resources = ExecutionTaskPhaseResources(sources, c.deps.authority)
    prep = TaskPreparationAuthority(sources, c.deps.runs, resources, store)
    cleanup = TaskFinalizationPlan(
        scope=reset.scope,
        browser_close_operation_id="original-browser-close",
        restore_operation_id="original-native-restore",
        resume_operation_id="original-native-resume",
        qualification_operation_id="original-reset-facts",
        reset_operation_id="original-safe-reset",
    )
    cleanup_source = UnitCleanupSource()
    final = TaskFinalizationAuthority(
        put(store, cleanup, cleanup.schema_version),
        sources,
        c.deps.runs,
        c.deps.claims,
        c.source.plans,
        cleanup_source,
        store,
    )

    class Preparation:
        def acquire(
            self,
            plan: TaskExecutionPlan,
            operation: OperationContext,
            control: OperationControl,
        ) -> tuple[EvidenceRef, ...]:
            prep.verify(plan, declaration, operation, control)
            return c.phases.acquire(plan, operation, control)

        def prepare(
            self,
            plan: TaskExecutionPlan,
            operation: OperationContext,
            control: OperationControl,
        ) -> tuple[EvidenceRef, ...]:
            prep.verify(plan, declaration, operation, control)
            return c.phases.prepare(plan, operation, control)

    class Finalization:
        def close(
            self,
            plan: TaskExecutionPlan,
            reset: ResetPlan,
            operation: OperationContext,
            control: OperationControl,
        ) -> ClosedTaskResources:
            final.verify(
                plan, cleanup, c.phases.closed.closure_refs, operation, control
            )
            return c.phases.close(plan, reset, operation, control)

        def restore(
            self,
            plan: TaskExecutionPlan,
            closed: ClosedTaskResources,
            operation: OperationContext,
            control: OperationControl,
        ) -> EvidenceRef:
            final.verify(plan, cleanup, closed.closure_refs, operation, control)
            return c.phases.restore(plan, closed, operation, control)

    c.deps = replace(c.deps, preparation=Preparation(), finalization=Finalization())
    return SinglePhaseCase(c, sources, resources, prep, final, cleanup_source)
