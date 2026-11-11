"""Convert completed task facts to the unchanged construction result wire."""

from lab_generate_skill.domain.construction import ConstructionAttemptResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.task_execution_result import (
    ExecutedTaskReceipt,
    TaskAttemptResult,
)
from .task_completion import CompletedTaskExecution
from .task_result_publication import publish_task_result


def construction_task_result(
    completed: CompletedTaskExecution,
) -> ConstructionAttemptResult:
    if completed.intent.source_kind != "construction":
        raise OwnershipConflict(
            "Construction result requires actual construction admission"
        )
    receipt = ExecutedTaskReceipt.model_validate(
        {
            **completed.facts.model_dump(exclude={"schema_version"}),
            "schema_version": "executed-task-receipt/1",
        }
    )
    return publish_task_result(
        completed,
        receipt,
        lambda ref: TaskAttemptResult(
            intent=completed.intent,
            execution_ref=ref,
            generations=completed.generations,
            interactions=completed.interactions,
        ),
        lambda ref: ConstructionAttemptResult(
            intent=completed.intent,
            attempt_ref=ref,
            evaluation=completed.evaluation,
            evaluation_ref=completed.facts.evaluation_ref,
            generations=completed.generations,
            interactions=completed.interactions,
        ),
    )
