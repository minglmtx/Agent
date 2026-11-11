"""System implementation of Clock, for injection into operation controls."""

import time
from datetime import datetime, timezone


class SystemClock:
    """UTC wall time plus monotonic durations; no scheduling/business policy."""

    def utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
