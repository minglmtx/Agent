"""One owner's explicit execution/cleanup limits; no scheduler or authority."""

from datetime import datetime, timedelta
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .lifecycle import ResourceOwner
from .validation import Contract


class OperationTimeWindow(Contract):
    schema_version: Literal["operation-time-window/1"] = "operation-time-window/1"
    owner: ResourceOwner
    execution_deadline: AwareDatetime
    cleanup_deadline: AwareDatetime
    hard_end: AwareDatetime

    @model_validator(mode="after")
    def ordered_limits(self) -> Self:
        if not self.execution_deadline < self.cleanup_deadline < self.hard_end:
            raise ValueError("Execution, cleanup and hard end must be strictly ordered")
        return self


class OperationWindowBudgets(Contract):
    """Caller-composed critical paths, not measured times or a production recipe.

    Execution includes its normal-path restoration. cleanup_seconds is the largest
    remaining serial abort/closure/review path, without counting nested work twice.
    Asset/setup time before construction must be budgeted by the actual caller.
    """

    schema_version: Literal["operation-window-budgets/1"] = "operation-window-budgets/1"
    execution_seconds: int = Field(gt=0, le=86400)
    cleanup_seconds: int = Field(gt=0, le=86400)
    final_margin_seconds: int = Field(gt=0, le=86400)
    stop_signal_lead_seconds: int = Field(gt=0, le=86400)

    @model_validator(mode="after")
    def signal_covers_cleanup(self) -> Self:
        if (
            self.stop_signal_lead_seconds
            < self.cleanup_seconds + self.final_margin_seconds
        ):
            raise ValueError(
                "Stop signal must leave cleanup and final margin before hard end"
            )
        return self

    @property
    def minimum_remaining_seconds(self) -> int:
        return self.execution_seconds + self.cleanup_seconds + self.final_margin_seconds

    def window(
        self, owner: ResourceOwner, *, now: datetime, hard_end: datetime
    ) -> OperationTimeWindow:
        selected = OperationWindowBudgets.model_validate(self)
        owner = ResourceOwner.model_validate(owner)
        # Validate timestamps through the boundary contract before arithmetic.
        candidate = OperationTimeWindow(
            owner=owner,
            execution_deadline=now,
            cleanup_deadline=hard_end
            - timedelta(seconds=selected.final_margin_seconds),
            hard_end=hard_end,
        )
        if (
            candidate.hard_end - now
        ).total_seconds() < selected.minimum_remaining_seconds:
            raise ValueError(
                "Insufficient job time for execution, cleanup and final margin"
            )
        if now >= hard_end - timedelta(seconds=selected.stop_signal_lead_seconds):
            raise ValueError("Stop signal boundary has already passed; no new work")
        return OperationTimeWindow(
            owner=owner,
            execution_deadline=now + timedelta(seconds=selected.execution_seconds),
            cleanup_deadline=candidate.cleanup_deadline,
            hard_end=candidate.hard_end,
        )
