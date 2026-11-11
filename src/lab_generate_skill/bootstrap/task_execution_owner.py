"""One bound task entry/owner scope over the sole application lifecycle."""

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from typing import Generic, TypeVar
from lab_generate_skill.application.execute_task import execute_task
from lab_generate_skill.application.initialized_task_entry import (
    execute_initialized_task,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.application.task_completion import CompletedTaskExecution
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.task_intent import TaskAttemptIntent
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.ports.task_execution_deps import TaskExecutionDeps

D = TypeVar("D", bound=TaskExecutionDeps)
R = TypeVar("R", bound=Contract)


class RecordedTaskExecution(Generic[D, R]):
    def __init__(
        self,
        plan: TaskExecutionPlan,
        deps: D,
        convert: Callable[[CompletedTaskExecution], R],
        *,
        resource_scope: Callable[[], AbstractContextManager[object]] | None = None,
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        self.deps, self.convert, self.resource_scope = deps, convert, resource_scope

    def _require_call(
        self, intent: TaskAttemptIntent, operation: OperationContext
    ) -> None:
        intent = TaskAttemptIntent.model_validate(intent)
        operation = OperationContext.model_validate(operation)
        if intent != self.plan.intent or operation != self.plan.operation:
            raise OwnershipConflict(
                "Task adapter changed original frozen intent/operation"
            )

    def execute(self, intent: TaskAttemptIntent, operation: OperationContext) -> R:
        self._require_call(intent, operation)
        return self._within_owner(lambda: execute_task(self.plan, self.deps))

    def execute_initialized(
        self,
        intent: TaskAttemptIntent,
        operation: OperationContext,
        initialized_ref: EvidenceRef,
        *,
        expected_revision: int,
    ) -> R:
        self._require_call(intent, operation)
        if self.resource_scope is None:
            raise ValueError(
                "Initialized task entry requires its original bounded resource-owner scope"
            )
        return self._within_owner(
            lambda: execute_initialized_task(
                self.plan,
                self.deps,
                initialized_ref,
                expected_revision=expected_revision,
            )
        )

    def _within_owner(self, consume: Callable[[], CompletedTaskExecution]) -> R:
        result: R | None = None
        try:
            # The current owner remains responsible before an acknowledged
            # lifecycle transition, and after any lost-ack/unknown failure.
            with (
                self.resource_scope()
                if self.resource_scope is not None
                else nullcontext()
            ):
                result = self.convert(consume())
            return result
        except BaseException as error:
            if result is not None:
                setattr(error, "known_task_result", result)
            raise
