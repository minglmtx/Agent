"""Intersect original operation guards with a fixed, owner-local time window.

OperationContext, cancellation and recovery identities remain unchanged. Cleanup
gets its own reserved window after execution stops, and cannot extend the job.
The deployment caller must verify the external hard end and budget its branches.
"""

import math
from contextlib import AbstractContextManager, nullcontext
from datetime import datetime, timedelta
from threading import Lock

from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.operation_window import OperationTimeWindow
from lab_generate_skill.domain.execution_stage_budget import (
    ExecutionStage,
    ExecutionStageBudgets,
)
from .execution_stages import ExecutionStages
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControl,
    OperationControls,
)


def _clock(clock: Clock) -> tuple[datetime, float]:
    now, elapsed = clock.utcnow(), clock.monotonic()
    if (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() is None
        or type(elapsed) not in (int, float)
    ):
        raise ValueError("Window requires aware wall and finite monotonic clocks")
    try:
        if not math.isfinite(elapsed):
            raise ValueError("Window monotonic clock must be finite")
    except OverflowError as error:
        raise ValueError("Window monotonic clock exceeds numeric range") from error
    return now, elapsed


class BoundedOperationControls:
    def __init__(
        self, controls: OperationControls, clock: Clock, window: OperationTimeWindow
    ) -> None:
        self.window = OperationTimeWindow.model_validate(window)
        self._controls, self._clock = controls, clock
        now, elapsed = _clock(clock)
        if self.window.execution_deadline <= now:
            raise ValueError("No execution window remains before creating consumers")
        # Capture both origins now. A newly bound child cannot gain time after
        # clock rollback, and cleanup retains its reserve after cancellation.
        self._expires = {
            mode: elapsed + (deadline - now).total_seconds()
            for mode, deadline in (
                ("execute", self.window.execution_deadline),
                ("cleanup", self.window.cleanup_deadline),
            )
        }
        self._execution_cutoff = (
            self.window.execution_deadline,
            self._expires["execute"],
        )
        self._bound: dict[str, _WindowControl] = {}
        self._lock = Lock()
        self._stages: ExecutionStages | None = None

    def configure_stages(
        self, operation: OperationContext, budgets: ExecutionStageBudgets
    ) -> None:
        operation = OperationContext.model_validate(operation)
        budgets = ExecutionStageBudgets.model_validate(budgets)
        if operation.mode != "execute":
            raise OwnershipConflict("Stage configuration requires original execution")
        remaining = self.bind(operation).checkpoint()
        if remaining < budgets.execution_seconds:
            raise ValueError(
                "Insufficient original parent window for declared stage budgets"
            )
        with self._lock:
            if self._stages is not None:
                raise OwnershipConflict("Original stage budgets already configured")
            self._stages = ExecutionStages(budgets, lambda: _clock(self._clock))

    def stage(
        self,
        name: ExecutionStage,
        operation: OperationContext,
        *,
        seconds: int | None = None,
    ) -> AbstractContextManager[None]:
        original = self.bind(operation)
        if self._stages is None:
            # Historical entry configurations did not select phase budgets.
            # Current budget/3 consumers require configure_stages before work.
            return nullcontext()
        return self._stages.enter(name, operation, original, seconds=seconds)

    @property
    def stage_observations(self) -> tuple[dict[str, object], ...]:
        return (
            ()
            if self._stages is None
            else tuple(dict(r) for r in self._stages.observations)
        )

    def require_execution_budget(
        self,
        operation: OperationContext,
        *,
        preparation_seconds: int,
        task_seconds: int,
    ) -> float:
        """Check a complete next task before claim, inside the reserved window.

        Does not claim work, extend time or acquire resources. The existing
        execution cutoff already excludes cleanup and the final margin.
        """
        for seconds in (preparation_seconds, task_seconds):
            if type(seconds) is not int or not 1 <= seconds <= 86400:
                raise ValueError(
                    "Explicit positive preparation and task budgets required"
                )
        operation = OperationContext.model_validate(operation)
        if operation.mode != "execute":
            raise OwnershipConflict("Only original execution may admit new work")
        remaining = self.bind(operation).checkpoint()
        if remaining < preparation_seconds + task_seconds:
            raise ValueError(
                "Insufficient time for preparation and complete task before cleanup"
            )
        return remaining

    def narrow_execution(
        self, operation: OperationContext, *, seconds: int
    ) -> OperationTimeWindow:
        """Start a smaller execution cap at an original caller's handoff.

        Every existing/future guard on this same controller sees the cap. This
        is useful for a single-member entry after model preparation; it cannot
        restore time for another member or extend any immutable operation,
        cancellation channel, cleanup reserve or external hard end.
        """
        if type(seconds) is not int or not 1 <= seconds <= 86400:
            raise ValueError("Explicit positive execution duration required")
        operation = OperationContext.model_validate(operation)
        if operation.mode != "execute":
            raise OwnershipConflict("Only original execution may narrow its window")
        original = self.bind(operation)
        original.checkpoint()
        with self._lock:
            # A task starts only with its complete selected budget remaining.
            if original.checkpoint() < seconds:
                raise ValueError("Insufficient remaining execution time for handoff")
            now, elapsed = _clock(self._clock)
            previous_deadline, previous_expires = self._execution_cutoff
            deadline = min(
                previous_deadline,
                operation.deadline,
                now + timedelta(seconds=seconds),
            )
            expires = min(previous_expires, elapsed + seconds)
            selected = OperationTimeWindow(
                owner=self.window.owner,
                execution_deadline=deadline,
                cleanup_deadline=self.window.cleanup_deadline,
                hard_end=self.window.hard_end,
            )
            self.window = selected
            self._execution_cutoff = deadline, expires
            return selected

    def bind(self, op: OperationContext) -> OperationControl:
        op = OperationContext.model_validate(op)
        if (op.run_id, op.owner_id) != (
            self.window.owner.run_id,
            self.window.owner.owner_id,
        ):
            raise OwnershipConflict("Time window belongs to another original owner")
        # Original registry enforces exact identity and cancellation semantics.
        original = self._controls.bind(op)
        with self._lock:
            value = self._bound.get(op.operation_id)
            if value is None:
                value = _WindowControl(self, original, op)
                self._bound[op.operation_id] = value
            elif value.operation != op:
                raise OwnershipConflict("Bound operation context changed")
            return value

    def _remaining(self, op: OperationContext) -> float:
        now, elapsed = _clock(self._clock)
        deadline, expires = (
            self._execution_cutoff
            if op.mode == "execute"
            else (self.window.cleanup_deadline, self._expires["cleanup"])
        )
        remaining = min((deadline - now).total_seconds(), expires - elapsed)
        if not math.isfinite(remaining) or remaining <= 0:
            raise OperationStopped("DEADLINE_EXCEEDED", op.operation_id)
        if self._stages is not None:
            phase_remaining = self._stages.remaining(op)
            if phase_remaining is not None:
                remaining = min(remaining, phase_remaining)
        return remaining


class _WindowControl:
    def __init__(
        self,
        window: BoundedOperationControls,
        original: OperationControl,
        operation: OperationContext,
    ) -> None:
        self._window, self._original, self.operation = window, original, operation

    def checkpoint(self) -> float:
        before = self._window._remaining(self.operation)
        remaining = self._original.checkpoint()
        try:
            if (
                type(remaining) not in (int, float)
                or not math.isfinite(remaining)
                or remaining <= 0
            ):
                raise ValueError("Original guard must return finite positive time")
        except OverflowError as error:
            raise ValueError("Original guard time exceeds numeric range") from error
        return min(before, remaining, self._window._remaining(self.operation))

    def wait(self, seconds: float) -> None:
        try:
            if (
                type(seconds) not in (int, float)
                or not math.isfinite(seconds)
                or seconds < 0
            ):
                raise ValueError("Wait duration must be finite and nonnegative")
        except OverflowError as error:
            raise ValueError("Wait duration exceeds numeric range") from error
        self._original.wait(min(seconds, self.checkpoint()))
        self.checkpoint()
