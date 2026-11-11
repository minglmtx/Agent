"""Read-only current source authority for explicitly selected initial adoption."""

import os
import threading
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.initial_adoption import InitialAdoptionInputs
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from .execution_task_source import OriginalExecutionTaskSource


class ExecutionInitialAdoptionAuthority:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        inputs: InitialAdoptionInputs,
        source: OriginalExecutionTaskSource,
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        self._inputs = InitialAdoptionInputs.model_validate(inputs)
        if not isinstance(source, OriginalExecutionTaskSource):
            raise TypeError("The existing current source reader is mandatory")
        if (
            self.plan.source_ref != self._inputs.binding.execution_source_ref
            or self.plan.intent != self._inputs.source.intent
        ):
            raise OwnershipConflict(
                "Adoption changed the current frozen task plan/source"
            )
        self.source = source
        self.owner = os.getpid(), threading.get_ident()

    @property
    def inputs(self) -> InitialAdoptionInputs:
        return self._inputs

    def verify_adoption(
        self,
        inputs: InitialAdoptionInputs,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        inputs = InitialAdoptionInputs.model_validate(inputs)
        operation = OperationContext.model_validate(operation)
        owner = self.plan.intent.binding.run.owner
        control.checkpoint()
        if (
            self.owner != (os.getpid(), threading.get_ident())
            or inputs != self.inputs
            or (operation.run_id, operation.owner_id) != (owner.run_id, owner.owner_id)
            or operation.attempt_id not in (None, self.plan.intent.binding.attempt_id)
        ):
            raise OwnershipConflict(
                "Initial adoption left its current caller/task selection"
            )
        # A derived read keeps the actual caller, deadline, mode and cancellation.
        # It has no current attempt/resource mutation identity or old-owner retag.
        read = operation.model_copy(
            update={
                "operation_id": operation.operation_id + ".initial-source",
                "attempt_id": None,
                "allocation_id": None,
                "recovery_ref": None,
            }
        )
        facts = self.source.load(self.plan, read, control)
        if (
            facts.source != inputs.source
            or facts.source.source_context_receipt_ref
            != inputs.binding.source_context_ref
        ):
            raise OwnershipConflict(
                "Adoption source differs from actual current claim/source"
            )
        self.source.recheck(self.plan, facts, read, control)
        control.checkpoint()
