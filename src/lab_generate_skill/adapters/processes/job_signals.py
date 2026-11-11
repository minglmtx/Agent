"""Original process signal channel; cleanup uses its own bounded controls."""

from datetime import datetime, timezone
import signal
from types import FrameType
from lab_generate_skill.domain.lifecycle import ResourceOwner, CancellationRef


class OriginalSignalCancellation:
    """SIGTERM/INT/USR1 set a real channel; cleanup remains independently bounded."""

    def __init__(self, owner: ResourceOwner) -> None:
        self.reference = CancellationRef(
            channel_id="original-production-signals",
            run_id=owner.run_id,
            owner_id=owner.owner_id,
        )
        self.signals: list[dict[str, object]] = []
        self.previous: dict[int, object] = {}

    def __enter__(self) -> "OriginalSignalCancellation":
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGUSR1):
            self.previous[number] = signal.signal(number, self._receive)
        return self

    def __exit__(self, *args: object) -> None:
        for number, previous in self.previous.items():
            # Stored handlers are exactly the objects returned by signal.signal.
            signal.signal(number, previous)  # type: ignore[arg-type]

    def _receive(self, number: int, frame: FrameType | None) -> None:
        self.signals.append(
            {"signal": number, "at": datetime.now(timezone.utc).isoformat()}
        )

    def is_cancelled(self, reference: CancellationRef) -> bool:
        if CancellationRef.model_validate(reference) != self.reference:
            raise ValueError("Cancellation reader changed its original live channel")
        return bool(self.signals)
