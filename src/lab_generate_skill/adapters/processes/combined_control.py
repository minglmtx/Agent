"""Intersect existing caller and operation guards; never create a new deadline."""

import math
from lab_generate_skill.ports.lifecycle import OperationControl


def _remaining(value: float) -> float:
    try:
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("Control must report a positive finite remaining duration")
        return float(value)
    except OverflowError as error:
        raise ValueError("Control duration exceeds numeric range") from error


class CombinedControl:
    def __init__(self, caller: OperationControl, bound: OperationControl) -> None:
        self._caller, self._bound = caller, bound

    def checkpoint(self) -> float:
        before = _remaining(self._bound.checkpoint())
        remaining = _remaining(self._caller.checkpoint())
        # A slow caller poll counts against the already bound operation.
        after = _remaining(self._bound.checkpoint())
        return min(before, remaining, after)

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
        self._caller.wait(min(seconds, self.checkpoint()))
        self.checkpoint()
