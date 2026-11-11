"""Construction binding selects its own result adapter, preserving the existing entry."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from lab_generate_skill.application.construction_task_result import (
    construction_task_result,
)
from lab_generate_skill.application.construction_task_deps import (
    ConstructionTaskExecutionDeps,
)
from lab_generate_skill.domain.construction import ConstructionAttemptResult
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from .task_execution_owner import RecordedTaskExecution


class RecordedConstructionTask(
    RecordedTaskExecution[ConstructionTaskExecutionDeps, ConstructionAttemptResult]
):
    def __init__(
        self,
        plan: TaskExecutionPlan,
        deps: ConstructionTaskExecutionDeps,
        *,
        resource_scope: Callable[[], AbstractContextManager[object]] | None = None,
    ) -> None:
        plan = TaskExecutionPlan.model_validate(plan)
        if plan.intent.source_kind != "construction":
            raise OwnershipConflict(
                "Construction binding cannot consume a single execution plan"
            )
        super().__init__(
            plan, deps, construction_task_result, resource_scope=resource_scope
        )
