"""Trusted worker process collection around the existing unique observations.

A fixed bootstrap selects the implementation, never a model/wire plugin. The
collector cannot replace an observation or issue Actor actions. It may attach
native read transport before navigation, retain facts after an actual return,
and reject further actions after sealing its terminal evidence. All callbacks
run on the original browser owner thread; background transport must be stopped
by close, including when attach or collection only partially completed.
"""

from typing import Any, Protocol, runtime_checkable
from lab_generate_skill.domain.browser_session import BrowserSessionSpec, BrowserReadout
from .lifecycle import OperationControl


@runtime_checkable
class BrowserProcessCollector(Protocol):
    def attach(
        self, page: Any, spec: BrowserSessionSpec, control: OperationControl
    ) -> None: ...

    def before_action(self, control: OperationControl) -> None:
        """Reject sealed/failed collection before any new browser side effect."""
        ...

    def observe(
        self, page: Any, readout: BrowserReadout, control: OperationControl
    ) -> None:
        """Retain facts bound to this already projected return; do not reobserve."""
        ...

    def close(self, control: OperationControl) -> None:
        """Stop original owned transport; safe after partial attach, idempotent."""
        ...
