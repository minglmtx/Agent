"""Owner-local temporary caps; never reset the parent clock or cleanup reserve."""

from contextlib import contextmanager
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
import os
import threading
from lab_generate_skill.domain.execution_stage_budget import (
    ExecutionStage,
    ExecutionStageBudgets,
    STAGES,
)
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl


class ExecutionStages:
    def __init__(
        self,
        budgets: ExecutionStageBudgets,
        clock: Callable[[], tuple[datetime, float]],
    ) -> None:
        self.budgets = ExecutionStageBudgets.model_validate(budgets)
        self.clock = clock
        self.owner = os.getpid(), threading.get_ident()
        self.used: set[tuple[str, str]] = set()
        self.completed: set[ExecutionStage] = set()
        self.active: tuple[datetime, float] | None = None
        self.observations: list[dict[str, object]] = []

    def remaining(self, operation: OperationContext) -> float | None:
        if self.active is None or operation.mode == "cleanup":
            return None
        now, elapsed = self.clock()
        deadline, expires = self.active
        remaining = min((deadline - now).total_seconds(), expires - elapsed)
        if remaining <= 0:
            raise OperationStopped("DEADLINE_EXCEEDED", operation.operation_id)
        return remaining

    @contextmanager
    def enter(
        self,
        stage: ExecutionStage,
        operation: OperationContext,
        control: OperationControl,
        *,
        seconds: int | None = None,
    ) -> Iterator[None]:
        if (
            self.owner != (os.getpid(), threading.get_ident())
            or operation.mode != "execute"
        ):
            raise OwnershipConflict(
                "Execution stage requires its original controller and execute scope"
            )
        if self.active is not None:
            raise OwnershipConflict("Execution stages cannot overlap or nest")
        limit = self.budgets.seconds(stage)
        if seconds is not None:
            if type(seconds) is not int or not 0 < seconds <= limit:
                raise ValueError(
                    "A stage override may only narrow its declared positive cap"
                )
            limit = seconds
        key = stage, operation.attempt_id or operation.run_id
        if key in self.used:
            raise DispatchAlreadyCommitted("Original execution stage already attempted")
        remaining = control.checkpoint()
        reserve = self.budgets.reserve_after(stage) - sum(
            self.budgets.seconds(done)
            for done in self.completed
            if STAGES.index(done) > STAGES.index(stage)
        )
        now, elapsed = self.clock()
        record: dict[str, object] = {
            "stage": stage,
            "operation_id": operation.operation_id,
            "run_id": operation.run_id,
            "attempt_id": operation.attempt_id,
            "started_at": now.isoformat(),
            "limit_seconds": limit,
            "downstream_reserved_seconds": reserve,
            "remaining_before_seconds": remaining,
        }
        self.observations.append(record)
        if remaining < limit + reserve:
            record.update(
                outcome="rejected_insufficient_time",
                ended_at=now.isoformat(),
                elapsed_seconds=0.0,
            )
            raise ValueError(
                "Insufficient execution time for stage and required downstream work: "
                + stage
            )
        # The control still intersects the original operation, monotonic parent
        # and job window. This temporary child cap cannot extend any of them.
        self.active = now + timedelta(seconds=limit), elapsed + limit
        self.used.add(key)
        primary: BaseException | None = None
        try:
            control.checkpoint()
            yield
            control.checkpoint()
            record["outcome"] = "completed"
            self.completed.add(stage)
        except BaseException as error:
            primary = error
            record["outcome"] = "unconfirmed"
            record["error_type"] = type(error).__name__
            raise
        finally:
            try:
                end, ended = self.clock()
                record.update(ended_at=end.isoformat(), elapsed_seconds=ended - elapsed)
            except BaseException as error:
                record["observation_error_type"] = type(error).__name__
                if primary is None:
                    raise
            finally:
                self.active = None
