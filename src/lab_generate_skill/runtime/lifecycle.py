"""Cooperative deadline/cancellation guard for a single bound operation.

Input: immutable OperationContext and injected Clock/CancellationReader. Output:
remaining duration or classified OperationStopped. A captured monotonic deadline
cannot be extended by a wall-clock rollback. This guard bounds polling and
operation boundaries; hard interruption of blocking native calls belongs to the
supervised-process adapter, not an unsafe worker thread.
"""

import math
from datetime import datetime
from threading import Lock

from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import CancellationReader, Clock


class OperationGuards:
    """Per-job guard registry; preserve monotonic origin across repeated calls."""

    def __init__(self, clock: Clock, cancellation: CancellationReader) -> None:
        self._clock = clock
        self._cancellation = cancellation
        self._guards: dict[tuple[str, str, str], OperationGuard] = {}
        self._lock = Lock()

    def bind(self, op: OperationContext) -> "OperationGuard":
        key = (op.run_id, op.owner_id, op.operation_id)
        with self._lock:
            guard = self._guards.get(key)
            if guard is None:
                guard = OperationGuard(op, self._clock, self._cancellation)
                self._guards[key] = guard
            elif guard.context != op:
                raise OwnershipConflict(
                    "Operation ID is already bound to another context"
                )
            return guard


class OperationGuard:
    """Create once per operation and retain across all its blocking boundaries."""

    def __init__(
        self, context: OperationContext, clock: Clock, cancellation: CancellationReader
    ) -> None:
        self.context = context
        self._clock = clock
        self._cancellation = cancellation
        now, monotonic = self._read_clock()
        self._expires = monotonic + max(0.0, (context.deadline - now).total_seconds())

    def _read_clock(self) -> tuple[datetime, float]:
        """Validate each provider reading before arithmetic can hide NaN/Inf."""
        now = self._clock.utcnow()
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise ValueError("Operation clock must return aware timestamps")
        monotonic = self._clock.monotonic()
        if isinstance(monotonic, bool) or not isinstance(monotonic, (int, float)):
            raise ValueError("Monotonic clock must return a finite number")
        try:
            if not math.isfinite(monotonic):
                raise ValueError("Monotonic clock must be finite")
        except OverflowError as error:
            raise ValueError(
                "Monotonic clock is outside the supported range"
            ) from error
        return now, monotonic

    def checkpoint(self) -> float:
        """Check stop facts before new effects; return remaining seconds."""
        context = self.context
        if context.cancellation_ref is not None and self._cancellation.is_cancelled(
            context.cancellation_ref
        ):
            raise OperationStopped("CANCELLED", context.operation_id)
        now, monotonic = self._read_clock()
        wall_remaining = (context.deadline - now).total_seconds()
        monotonic_remaining = self._expires - monotonic
        remaining = min(wall_remaining, monotonic_remaining)
        if not math.isfinite(remaining) or remaining <= 0:
            raise OperationStopped("DEADLINE_EXCEEDED", context.operation_id)
        return remaining

    def wait(self, seconds: float) -> None:
        """Bound a pause; reject invalid numeric/type inputs before any sleep."""
        if not isinstance(seconds, (int, float)):
            raise TypeError("Wait duration must be an int or float")
        try:
            if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds < 0:
                raise ValueError("Wait duration must be nonnegative and finite")
        except OverflowError as error:
            raise ValueError("Wait duration is outside the supported range") from error
        self._clock.sleep(min(seconds, self.checkpoint()))
        self.checkpoint()
