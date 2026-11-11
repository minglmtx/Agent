"""Mandatory permissions and independent facts for one original site resource.

Spawn admission verifies frozen release/assets/run/source/token. Ready admission
checks actual original CPU domain before its acquisition is persisted. Started
admission verifies readiness only; no implied baseline/TaskFamily permission.
Closure covers original processes and declared residual files/disposition, never
just the transport. Unknown proof must reject or return unconfirmed. Persisted
objects and kernel facts must be checked by the production implementation.
"""

from typing import Protocol
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceReady,
    SiteResourceAttempt,
    SiteStepClosed,
)
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.process_identity import ProcessTermination
from .site_worker import SiteWorkerAuthority
from .lifecycle import OperationControl


class SiteResourceAuthority(SiteWorkerAuthority, Protocol):
    def authorize_spawn(
        self,
        spec: SiteResourceSpec,
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...
    def verify_ready(
        self,
        spec: SiteResourceSpec,
        ready: SiteResourceReady,
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...
    def verify_started(
        self,
        spec: SiteResourceSpec,
        ready: SiteResourceReady,
        started: SiteInstanceStarted,
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...
    def verify_closed(
        self,
        spec: SiteResourceSpec,
        attempt: SiteResourceAttempt,
        termination: ProcessTermination | None,
        step: SiteStepClosed | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt: ...


class SiteOriginAuthority(Protocol):
    def verify_origin(
        self,
        spec: SiteResourceSpec,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Read original qualified source origin before worker/staging effects.

        Origin equality does not grant original source/lease/physical rights or
        prove that the prior entire worker domain has closed.
        """
        ...
