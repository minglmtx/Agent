"""Already captured public geometry; reading it performs no browser action."""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.observation_viewport import ObservationViewport


@runtime_checkable
class BrowserViewportSource(Protocol):
    @property
    def viewport(self) -> ObservationViewport | None: ...
