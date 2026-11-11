"""Delegate recorded leaf reads without dropping the enclosing review guard."""

import math
from lab_generate_skill.ports.lifecycle import OperationControl


class ReviewControl:
    def __init__(self, original: OperationControl, leaf: OperationControl) -> None:
        self.original, self.leaf = original, leaf

    def checkpoint(self) -> float:
        return min(self.original.checkpoint(), self.leaf.checkpoint())

    def wait(self, seconds: float) -> None:
        if (
            type(seconds) not in (int, float)
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise ValueError("Finite nonnegative review wait required")
        remaining = seconds
        self.checkpoint()
        while remaining > 0:
            step = min(remaining, self.checkpoint(), 0.1)
            self.leaf.wait(step)
            remaining -= step
            self.checkpoint()
