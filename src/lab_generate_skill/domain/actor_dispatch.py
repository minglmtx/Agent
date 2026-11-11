"""One Actor generation intent and its independent result recording command."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .errors import OwnershipConflict
from .lifecycle import OperationContext
from .trace_events import GenerationPlanned
from .validation import Contract


class ActorDispatch(Contract):
    schema_version: Literal["actor-dispatch/1"] = "actor-dispatch/1"
    intent: GenerationPlanned
    expected_revision: int = Field(ge=0)
    result_operation: OperationContext

    @model_validator(mode="after")
    def original_generation_and_independent_result(self) -> Self:
        command = self.intent.operation
        execute = self.intent.intent.operation
        result = self.result_operation
        if command.mode != "execute" or execute.mode != "execute":
            raise ValueError("Cleanup cannot dispatch a new Actor generation")
        if any(
            (op.run_id, op.owner_id, op.attempt_id)
            != (execute.run_id, execute.owner_id, execute.attempt_id)
            for op in (command, result)
        ):
            raise OwnershipConflict("Actor commands must retain the original attempt")
        if len({op.operation_id for op in (command, execute, result)}) != 3:
            raise ValueError("Intent, execution and result commands must be distinct")
        if (
            result.mode != "cleanup"
            or result.parent_operation_id != execute.operation_id
            or result.cancellation_ref is not None
            or (result.allocation_id, result.recovery_ref)
            != (execute.allocation_id, execute.recovery_ref)
        ):
            raise OwnershipConflict(
                "Actor result recording requires independent original-call cleanup"
            )
        if self.intent.intent.execution_window is not None:
            seconds = (result.deadline - execute.deadline).total_seconds()
            retention = (
                self.intent.intent.execution_window.budgets.retention_seconds or 0
            )
            if not 0 < seconds - retention <= 60:
                raise ValueError(
                    "Selected call result must retain bounded original cleanup"
                )
        return self
