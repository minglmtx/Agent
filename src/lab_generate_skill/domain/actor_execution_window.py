"""Selected generation windows and actual dispatch facts; neither grants a send."""

import hashlib
from datetime import datetime, timedelta
from typing import Literal, Any
from pydantic import (
    AwareDatetime,
    Field,
    model_serializer,
    SerializerFunctionWrapHandler,
    model_validator,
)
from .validation import Contract
from .lifecycle import OperationContext


class ActorGenerationBudgets(Contract):
    schema_version: Literal["actor-generation-budgets/1"] = "actor-generation-budgets/1"
    preparation_seconds: int = Field(ge=1, le=3600)
    execution_seconds: int = Field(ge=1, le=600)

    # Explicit return persistence window. Omission preserves historical wire bytes.
    retention_seconds: int | None = Field(default=None, ge=1, le=600)

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value = dict(handler(self))
        if self.retention_seconds is None:
            value.pop("retention_seconds", None)
        return value

    def return_seconds(self, legacy_cleanup: int) -> int:
        return (
            legacy_cleanup if self.retention_seconds is None else self.retention_seconds
        )

    def result_ceiling_seconds(self, trace_cleanup: int) -> int:
        # Legacy calls shared their fixed return ceiling with trace publication.
        return trace_cleanup + (self.retention_seconds or 0)

    def round_seconds(self, interaction: int, cleanup: int) -> int:
        return (
            self.transaction_seconds
            + interaction
            + 4 * cleanup
            + self.return_seconds(cleanup)
        )

    @property
    def transaction_seconds(self) -> int:
        return self.preparation_seconds + self.execution_seconds


class ActorGenerationWindow(Contract):
    schema_version: Literal[
        "actor-generation-window/1", "actor-generation-window/2"
    ] = "actor-generation-window/1"
    budgets: ActorGenerationBudgets
    prepared_at: AwareDatetime
    preparation_limit_seconds: int | None = Field(default=None, ge=1, le=3600)

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value = dict(handler(self))
        if self.schema_version == "actor-generation-window/1":
            value.pop("preparation_limit_seconds", None)
        return value

    @model_validator(mode="after")
    def explicit_preparation_limit(self) -> "ActorGenerationWindow":
        if (self.schema_version == "actor-generation-window/2") != (
            self.preparation_limit_seconds is not None
        ):
            raise ValueError(
                "Effective preparation limit requires its explicit window version"
            )
        if (
            self.preparation_limit_seconds is not None
            and self.preparation_limit_seconds > self.budgets.preparation_seconds
        ):
            raise ValueError(
                "Effective preparation cannot enlarge the configured maximum"
            )
        return self

    @property
    def effective_preparation_seconds(self) -> int:
        return (
            self.budgets.preparation_seconds
            if self.preparation_limit_seconds is None
            else self.preparation_limit_seconds
        )

    @property
    def transaction_seconds(self) -> int:
        return self.effective_preparation_seconds + self.budgets.execution_seconds

    def require_original(self, original: OperationContext) -> None:
        if (
            original.mode != "execute"
            or original.deadline
            != self.prepared_at + timedelta(seconds=self.transaction_seconds)
        ):
            raise ValueError(
                "Original transaction must bind the complete selected windows"
            )

    def dispatch_operation(
        self, original: OperationContext, started_at: datetime
    ) -> OperationContext:
        if started_at.tzinfo is None or started_at.utcoffset() is None:
            raise ValueError("Aware original dispatch clock required")
        self.require_original(original)
        deadline = started_at + timedelta(seconds=self.budgets.execution_seconds)
        if started_at < self.prepared_at or deadline > original.deadline:
            raise ValueError(
                "Original transaction cannot fit the full execution window"
            )
        return OperationContext.model_validate(
            original.model_copy(
                update={
                    "operation_id": "actor-send-"
                    + hashlib.sha256(original.operation_id.encode()).hexdigest(),
                    "parent_operation_id": original.operation_id,
                    "deadline": deadline,
                }
            )
        )


class ActorDispatchTiming(Contract):
    schema_version: Literal["actor-dispatch-timing/1"] = "actor-dispatch-timing/1"
    started_at: AwareDatetime
    operation: OperationContext

    def require_original(
        self, original: OperationContext, selected: ActorGenerationWindow
    ) -> None:
        if self.operation != selected.dispatch_operation(original, self.started_at):
            raise ValueError(
                "Dispatch changed its original identity or selected window"
            )
