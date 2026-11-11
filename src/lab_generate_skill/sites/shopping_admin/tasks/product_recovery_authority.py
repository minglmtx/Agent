"""Bind state primitives to the current parent-authorized worker command.

This is a delegated command boundary, not production source/writer authority.
The fixed worker must already have verified original parent/installation and the
parent must admit each task request before sending. No independent restore right.
"""

from typing import Literal
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from ..state_contract import AdminStatePlan, AdminStateSnapshot


class ProductRecoveryAuthority:
    def __init__(self, plan: AdminStatePlan) -> None:
        self.plan = plan
        self.current: SiteTaskRequest | None = None
        self.snapshot: AdminStateSnapshot | None = None

    def verify(
        self,
        plan: AdminStatePlan,
        phase: Literal["save", "restore"],
        snapshot: AdminStateSnapshot | None,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if (
            plan != self.plan
            or self.current is None
            or self.current.action != ("snapshot" if phase == "save" else "restore")
        ):
            raise PermissionError("State operation has no original delegated command")
        if (phase == "save" and snapshot is not None) or (
            phase == "restore" and (self.snapshot is None or snapshot != self.snapshot)
        ):
            raise PermissionError("State operation changed original snapshot")
