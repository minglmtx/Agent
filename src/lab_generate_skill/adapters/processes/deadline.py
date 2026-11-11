"""Local monotonic child/cleanup deadline, never an operation identity extension."""

import math
import time
from lab_generate_skill.domain.errors import OperationStopped


class DeadlineControl:
    def __init__(self, seconds: float, operation_id: str) -> None:
        if (
            type(seconds) not in (int, float)
            or not math.isfinite(seconds)
            or not 0 < seconds <= 86400
        ):
            raise ValueError("Local deadline must be finite and in (0,86400]")
        self._expires = time.monotonic() + seconds
        self._operation_id = operation_id

    def checkpoint(self) -> float:
        remaining = self._expires - time.monotonic()
        if remaining <= 0:
            raise OperationStopped("DEADLINE_EXCEEDED", self._operation_id)
        return remaining

    def wait(self, seconds: float) -> None:
        if (
            type(seconds) not in (int, float)
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise ValueError("Local wait must be finite and nonnegative")
        time.sleep(min(seconds, self.checkpoint()))
        self.checkpoint()
