"""Single-task binding selects actual execution admission/result, without training roles."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from lab_generate_skill.application.execution_task_result import execution_task_result
from lab_generate_skill.application.execution_task_deps import (
    ExecutionTaskExecutionDeps,
)
from lab_generate_skill.domain.execution_task_result import ExecutionTaskResult
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from .task_execution_owner import RecordedTaskExecution


class RecordedExecutionTask(
    RecordedTaskExecution[ExecutionTaskExecutionDeps, ExecutionTaskResult]
):
    def __init__(
        self,
        plan: TaskExecutionPlan,
        deps: ExecutionTaskExecutionDeps,
        *,
        resource_scope: Callable[[], AbstractContextManager[object]] | None = None,
    ) -> None:
        plan = TaskExecutionPlan.model_validate(plan)
        if plan.intent.source_kind != "execution":
            raise OwnershipConflict(
                "Single execution binding cannot consume a construction plan"
            )
        super().__init__(
            plan, deps, execution_task_result, resource_scope=resource_scope
        )
