"""Convert completed single-task facts to an explicit non-training execution result."""

from lab_generate_skill.domain.execution_task_result import ExecutionTaskResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.task_execution_result import (
    ExecutedTaskReceipt,
    TaskAttemptResult,
)
from .task_completion import CompletedTaskExecution
from .task_result_publication import publish_task_result


def execution_task_result(completed: CompletedTaskExecution) -> ExecutionTaskResult:
    if completed.intent.source_kind != "execution":
        raise OwnershipConflict("Single result requires actual single-task admission")
    receipt = ExecutedTaskReceipt.model_validate(
        {
            **completed.facts.model_dump(exclude={"schema_version"}),
            "schema_version": "executed-task-receipt/2",
        }
    )
    return publish_task_result(
        completed,
        receipt,
        lambda ref: TaskAttemptResult(
            schema_version="execution-attempt-result/1",
            intent=completed.intent,
            execution_ref=ref,
            generations=completed.generations,
            interactions=completed.interactions,
        ),
        lambda ref: ExecutionTaskResult(
            intent=completed.intent,
            attempt_ref=ref,
            evaluation=completed.evaluation,
            evaluation_ref=completed.facts.evaluation_ref,
            generations=completed.generations,
            interactions=completed.interactions,
        ),
    )
