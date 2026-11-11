"""Construct the original initializer only after its preparation facts exist."""

import os
import threading
from collections.abc import Callable
from typing import Generic, TypeVar
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.task_execution import TaskInitialization

Initializer = TypeVar("Initializer", bound=TaskInitialization)


class DeferredTaskInitialization(Generic[Initializer]):
    """One original producer, not a runner, retry or speculative initialization.

    The composition-owned factory freezes actual prepared references and retains
    any partially constructed resource for the original finalizer. It must not
    launch another attempt or hide factory failure behind a replacement object.
    """

    def __init__(
        self,
        plan: TaskExecutionPlan,
        factory: Callable[
            [TaskExecutionPlan, OperationContext, OperationControl], Initializer
        ],
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        if not callable(factory):
            raise TypeError("An explicit original initialization factory is required")
        self.factory, self.attempted = factory, False
        self.producer: Initializer | None = None
        self.owner = os.getpid(), threading.get_ident()

    def original(self) -> Initializer:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Initialization changed original controller")
        if self.producer is None:
            raise OwnershipConflict("Original initializer has not been constructed")
        return self.producer

    def start(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> InitializedTask:
        plan = TaskExecutionPlan.model_validate(plan)
        operation = OperationContext.model_validate(operation)
        expected = self.plan.operation.model_copy(
            update={"operation_id": self.plan.operation.operation_id + ".starting"}
        )
        if (
            self.owner != (os.getpid(), threading.get_ident())
            or plan != self.plan
            or operation != expected
        ):
            raise OwnershipConflict(
                "Deferred initialization requires original starting phase"
            )
        if self.attempted:
            raise DispatchAlreadyCommitted(
                "Original initialization construction already attempted"
            )
        self.attempted = True
        control.checkpoint()
        producer = self.factory(plan, operation, control)
        if producer is None or not callable(getattr(producer, "start", None)):
            raise TypeError(
                "Factory must return the original TaskInitialization producer"
            )
        self.producer = producer
        return InitializedTask.model_validate(producer.start(plan, operation, control))
