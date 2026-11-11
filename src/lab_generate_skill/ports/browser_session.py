"""Raw browser capability for local or supervised implementations.

No page/backend handles or persistence. Publication consumes this port; only a
separately registered launcher may start a physical worker. Quarantine prevents
new actions but must preserve independent close and obtained readout facts.
"""

from typing import Literal, Protocol
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec, BrowserReadout
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl

BrowserState = Literal["new", "busy", "ready", "terminal", "quarantined", "closed"]


class RawBrowserSession(Protocol):
    @property
    def spec(self) -> BrowserSessionSpec: ...
    @property
    def state(self) -> BrowserState: ...
    @property
    def last_readout(self) -> BrowserReadout | None: ...
    def start(
        self, operation: OperationContext, *, control: OperationControl
    ) -> BrowserReadout: ...
    def step(
        self,
        action: BrowserAction,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> BrowserReadout: ...
    def quarantine(self) -> None: ...
    def close(
        self, operation: OperationContext, *, control: OperationControl
    ) -> None: ...
