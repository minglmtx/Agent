"""Mandatory browser launch and closure authority; no permissive defaults.

authorize_start verifies original release/assets/run/source/allocation before
spawn. verify_started independently checks the actual original process/resource
and initial evidence. verify_closed must verify all original browser resources,
not only a reaped leader; incomplete proof returns unconfirmed/failed or raises.
Website restoration is a separate site/task responsibility. Per-action authority
is inherited and must remain bound to this exact resource, including cleanup.
"""

from typing import Protocol
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceSpec,
    BrowserResourceStarted,
    BrowserResourceAttempt,
)
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.domain.browser_step import BrowserStepClosed
from .browser_authority import BrowserAuthority
from .lifecycle import OperationControl


class BrowserResourceAuthority(BrowserAuthority, Protocol):
    def authorize_start(
        self,
        spec: BrowserResourceSpec,
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...
    def verify_started(
        self,
        spec: BrowserResourceSpec,
        started: BrowserResourceStarted,
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...
    def verify_closed(
        self,
        spec: BrowserResourceSpec,
        attempt: BrowserResourceAttempt,
        termination: ProcessTermination | None,
        step: BrowserStepClosed | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt: ...
