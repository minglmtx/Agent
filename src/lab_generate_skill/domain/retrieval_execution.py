"""Immutable encoding facts bound to the original query/scope and operation."""

from typing import Literal, Self
from pydantic import model_validator
from .encoding import EncodedScores
from .errors import OwnershipConflict
from .lifecycle import OperationContext
from .retrieval import RetrievalQuery, RetrievalScope
from .validation import Contract


class RetrievalExecution(Contract):
    schema_version: Literal["retrieval-execution/1"] = "retrieval-execution/1"
    query: RetrievalQuery
    scope: RetrievalScope
    operation: OperationContext
    encoded: EncodedScores

    @model_validator(mode="after")
    def original_execution(self) -> Self:
        if self.operation.mode != "execute" or self.operation.attempt_id is not None:
            raise ValueError("Encoding facts need original run-level execute operation")
        return self

    def check_reconciliation(self, op: OperationContext) -> None:
        op = OperationContext.model_validate(op)
        if (op.run_id, op.owner_id, op.attempt_id) != (
            self.operation.run_id,
            self.operation.owner_id,
            None,
        ):
            raise OwnershipConflict("Reconciliation must retain original run/owner")
        if (
            op.mode == "cleanup"
            and op.parent_operation_id != self.operation.operation_id
        ):
            raise OwnershipConflict(
                "Cleanup reconciliation must identify original encoding operation"
            )
