"""One browser action's existing trace intent and independent result command.

This request is not an execution permit. The live trace journal acknowledges a
new ActionPlanned once; the browser capability must retain real resource/claim
permission. No payload or observation is reconstructed from an exception.
"""

from typing import Literal, Self
from pydantic import Field, model_validator
from .errors import OwnershipConflict
from .lifecycle import OperationContext
from .trace_events import ActionPlanned
from .validation import Contract


class BrowserDispatch(Contract):
    schema_version: Literal["browser-dispatch/1"] = "browser-dispatch/1"
    intent: ActionPlanned
    expected_revision: int = Field(ge=0)
    result_operation: OperationContext

    @model_validator(mode="after")
    def original_action_and_independent_result(self) -> Self:
        intent, result = self.intent, self.result_operation
        command, execute = intent.operation, intent.execution_operation
        if intent.decision.outcome != "action" or intent.decision.action is None:
            raise ValueError("Browser dispatch requires an already parsed action")
        if command.mode != "execute" or execute.mode != "execute":
            raise ValueError("Cleanup cannot dispatch a new browser action")
        if execute.attempt_id is None or any(
            (op.run_id, op.owner_id, op.attempt_id)
            != (execute.run_id, execute.owner_id, execute.attempt_id)
            for op in (command, result)
        ):
            raise OwnershipConflict("Browser commands must retain the same attempt")
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
                "Result recording requires independent cleanup of the original action"
            )
        return self
