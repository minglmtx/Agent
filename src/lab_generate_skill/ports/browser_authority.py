"""Mandatory live browser-resource authority; a declaration is not permission.

Verify original registered resource, caller, run/source claim, release/assets,
allowed protocol/actions and capture admission before start/step. Close uses
independent cleanup and must remain possible after the run has stopped. The
engine cannot turn this callback into original-resource termination proof.
"""

from typing import Literal, Protocol
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl


class BrowserAuthority(Protocol):
    def verify(
        self,
        spec: BrowserSessionSpec,
        phase: Literal["start", "step", "close"],
        action: BrowserAction | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...
