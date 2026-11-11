"""Read-only original browser facts used by trace and complete-state checks."""

from typing import Protocol
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.browser_session import BrowserReadout


class OriginalMapTerminal(Protocol):
    @property
    def initial(self) -> InitialObservationInputs: ...
    @property
    def intent(self) -> BrowserCaptureIntent: ...
    @property
    def result(self) -> BrowserCaptureResult: ...
    @property
    def readout(self) -> BrowserReadout: ...
