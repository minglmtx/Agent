"""One readonly dispatch in the original trace; not a browser/action permit."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .errors import OwnershipConflict
from .lifecycle import OperationContext
from .trace_events import ReadPlanned
from .validation import Contract


class ObservationReadDispatch(Contract):
    schema_version: Literal["observation-read-dispatch/1"] = (
        "observation-read-dispatch/1"
    )
    intent: ReadPlanned
    expected_revision: int = Field(ge=0)
    result_operation: OperationContext

    @model_validator(mode="after")
    def original_read_commands(self) -> Self:
        intent, execute, result = (
            self.intent.operation,
            self.intent.execution_operation,
            self.result_operation,
        )
        if intent.mode != "execute" or execute.mode != "execute":
            raise ValueError("Cleanup cannot dispatch a new observation reading")
        if execute.attempt_id is None or any(
            (op.run_id, op.owner_id, op.attempt_id)
            != (execute.run_id, execute.owner_id, execute.attempt_id)
            for op in (intent, result)
        ):
            raise OwnershipConflict(
                "Reading commands changed original task/owner/attempt"
            )
        if len({op.operation_id for op in (intent, execute, result)}) != 3:
            raise ValueError(
                "Reading intent, execution and result need distinct operation identities"
            )
        if (
            result.mode != "cleanup"
            or result.parent_operation_id != execute.operation_id
            or result.cancellation_ref is not None
            or (result.allocation_id, result.recovery_ref)
            != (execute.allocation_id, execute.recovery_ref)
        ):
            raise OwnershipConflict(
                "Original reading result requires its independent bounded cleanup command"
            )
        return self
