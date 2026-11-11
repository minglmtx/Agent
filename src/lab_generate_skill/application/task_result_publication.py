"""Append a business adapter's exact original envelopes; never choose a business mode."""

from collections.abc import Callable
from typing import TypeVar
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task_execution_result import (
    ExecutedTaskReceipt,
    TaskAttemptResult,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.validation import Contract
from .task_completion import CompletedTaskExecution
from .execute_task import TaskExecutionUnconfirmed

R = TypeVar("R", bound=Contract)


def publish_task_result(
    completed: CompletedTaskExecution,
    receipt: ExecutedTaskReceipt,
    envelope: Callable[[EvidenceRef], TaskAttemptResult],
    result: Callable[[EvidenceRef], R],
) -> R:
    try:
        if receipt.model_dump(exclude={"schema_version"}) != completed.facts.model_dump(
            exclude={"schema_version"}
        ):
            raise OwnershipConflict(
                "Business result changed original complete lifecycle facts"
            )
        events = completed.events
        op = events.operation("result", cleanup=True)
        execution_ref = events.put("execution", receipt, op)
        attempt = envelope(execution_ref)
        if (
            attempt.intent != completed.intent
            or attempt.execution_ref != execution_ref
            or (attempt.generations, attempt.interactions)
            != (completed.generations, completed.interactions)
        ):
            raise OwnershipConflict("Business envelope changed original task outcome")
        attempt_ref = events.put("attempt", attempt, op)
        return result(attempt_ref)
    except BaseException as error:
        raise TaskExecutionUnconfirmed(
            completed.plan,
            error,
            (),
            completed.events,
            completed.initialized,
            completed.trace,
            completed.evaluation,
        ) from error
