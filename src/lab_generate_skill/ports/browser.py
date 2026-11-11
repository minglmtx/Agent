"""The action capability of an already initialized, captured browser session.

step receives exact protocol text, the original execution identity and live
control. Implementations verify current resource/claim authority and supported
syntax before actions; collector attachment must already precede navigation.
Return StepResult only for an actual environment return, with published new
observation/raw-return references. Missing replies raise; never retry a step.

This capability does not own start/close/reset. Those belong to the surrounding
session lifecycle; implementing this protocol alone does not implement a full
BrowserSession or prove real browser supervision.
"""

from typing import Protocol
from lab_generate_skill.domain.browser import BrowserAction, StepResult
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl


class BrowserActions(Protocol):
    def step(
        self,
        action: BrowserAction,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> StepResult: ...
