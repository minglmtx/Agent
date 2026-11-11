"""Bind private physical I/O identities without reading caller-control internals.

An evidence operation describes one bounded CAS exchange, not a new model/task
execution or user authorization. Its run/source binding is supplied by trusted
bootstrap. The caller's control is retained and polled on every boundary; the
physical ceiling may shorten, never extend, its remaining budget. Workers still
need outer supervision for blocking I/O, control providers and launch itself.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from pydantic import TypeAdapter

from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from lab_generate_skill.domain.lifecycle import CancellationRef, OperationContext
from lab_generate_skill.domain.validation import Identifier
from lab_generate_skill.ports.lifecycle import Clock, OperationControl
from .lifecycle import OperationGuard


def _seconds(value: float) -> float:
    if type(value) not in (int, float):
        raise TypeError("Storage control durations must be exact int or float")
    try:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Storage control durations must be positive and finite")
    except OverflowError as error:
        raise ValueError(
            "Storage control duration is outside its numeric range"
        ) from error
    return float(value)


class _NoPrivateCancellation:
    def is_cancelled(self, reference: CancellationRef) -> bool:
        raise AssertionError(
            "Private storage operations use the original caller control"
        )


def _monotonic(clock: Clock) -> float:
    value = clock.monotonic()
    if type(value) not in (int, float):
        raise ValueError("Storage monotonic clock must return a finite number")
    try:
        if not math.isfinite(value):
            raise ValueError("Storage monotonic clock must be finite")
    except OverflowError as error:
        raise ValueError(
            "Storage monotonic clock is outside its numeric range"
        ) from error
    return float(value)


class _BoundIOControl:
    def __init__(
        self,
        caller: OperationControl,
        ceiling: OperationGuard,
        clock: Clock,
        started: float,
        budget: float,
    ) -> None:
        self._caller, self._ceiling = caller, ceiling
        self._clock, self._started, self._budget = clock, started, budget

    def _remaining(self) -> float:
        wall_bound = self._ceiling.checkpoint()
        elapsed = _monotonic(self._clock) - self._started
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("Storage monotonic elapsed time is invalid")
        remaining = self._budget - elapsed
        if remaining <= 0:
            raise OperationStopped(
                "DEADLINE_EXCEEDED", self._ceiling.context.operation_id
            )
        return min(wall_bound, remaining)

    def checkpoint(self) -> float:
        self._remaining()
        remaining = _seconds(self._caller.checkpoint())
        # Polling the original provider may itself consume time.
        return min(remaining, self._remaining())

    def wait(self, seconds: float) -> None:
        if type(seconds) not in (int, float):
            raise TypeError("Wait duration must be an exact int or float")
        try:
            if not math.isfinite(seconds) or seconds < 0:
                raise ValueError("Wait duration must be finite and nonnegative")
        except OverflowError as error:
            raise ValueError("Wait duration is outside its numeric range") from error
        self._caller.wait(min(seconds, self.checkpoint()))
        self.checkpoint()


@dataclass(frozen=True)
class PreparedEvidenceOperation:
    operation: OperationContext
    control: OperationControl

    def bind(self, op: OperationContext) -> OperationControl:
        """OperationControls for this invocation only; no deadline rebinding."""
        op = OperationContext.model_validate(op)
        if op != self.operation:
            raise OwnershipConflict(
                "Storage control belongs to another exact operation"
            )
        return self.control


class EvidenceOperations:
    def __init__(
        self, binding: EvidenceSessionBinding, clock: Clock, *, max_io_seconds: float
    ) -> None:
        self._binding = EvidenceSessionBinding.model_validate(binding)
        self._clock = clock
        self._maximum = _seconds(max_io_seconds)
        if self._maximum > 86400:
            raise ValueError("Physical evidence exchange ceiling cannot exceed one day")
        self._seen: set[str] = set()
        self._lock = Lock()

    @property
    def binding(self) -> EvidenceSessionBinding:
        return self._binding

    def prepare(
        self, exchange_id: str, control: OperationControl
    ) -> PreparedEvidenceOperation:
        exchange_id = TypeAdapter(Identifier).validate_python(exchange_id, strict=True)
        with self._lock:
            if exchange_id in self._seen:
                raise OwnershipConflict(
                    "Exchange already prepared; retain its original operation"
                )
            self._seen.add(exchange_id)
        # No clock/cancellation/provider work occurs while holding the local lock.
        # This set is not durable admission. Session.begin remains mandatory.
        monotonic_started = _monotonic(self._clock)
        started = self._clock.utcnow()
        if (
            not isinstance(started, datetime)
            or started.tzinfo is None
            or started.utcoffset() is None
        ):
            raise ValueError("Storage clock must return an aware timestamp")
        remaining = min(_seconds(control.checkpoint()), self._maximum)
        try:
            deadline = started + timedelta(seconds=remaining)
        except OverflowError as error:
            raise ValueError(
                "Storage deadline is outside the timestamp range"
            ) from error
        identity = hashlib.sha256(
            json.dumps(
                [self.binding.namespace_key, exchange_id], separators=(",", ":")
            ).encode()
        ).hexdigest()
        operation = OperationContext(
            operation_id="evidence-io-" + identity,
            run_id=self.binding.owner.run_id,
            owner_id=self.binding.owner.owner_id,
            deadline=deadline,
        )
        ceiling = OperationGuard(operation, self._clock, _NoPrivateCancellation())
        # Wall time can roll back during the first caller checkpoint, before
        # OperationGuard captures its own monotonic origin. Keep the earlier
        # physical origin as well so that poll time never extends this budget.
        bound = _BoundIOControl(
            control, ceiling, self._clock, monotonic_started, remaining
        )
        bound.checkpoint()
        return PreparedEvidenceOperation(operation, bound)
