"""Delegate read-only held-snapshot verification to the current native guard."""

from typing import Literal
from lab_generate_skill.ports.lifecycle import OperationControl
from ..service_contract import AdminServiceSpec
from ..search_contract import AdminSearchSnapshot
from .product_recovery_authority import ProductRecoveryAuthority
from .product_search_authority import ProductSearchAuthority


class NavigationSearchAuthority:
    def __init__(self, parent: ProductRecoveryAuthority) -> None:
        self.parent = parent
        self.state = ProductSearchAuthority(parent)

    def verify(
        self,
        service: AdminServiceSpec,
        phase: Literal["save", "verify", "preflight", "restore"],
        snapshot: AdminSearchSnapshot | None,
        control: OperationControl,
    ) -> None:
        current, saved = self.parent.current, self.parent.snapshot
        if phase == "verify" and current is not None and current.action == "inspect":
            control.checkpoint()
            if (
                current.operation.mode != "execute"
                or saved is None
                or service != self.parent.plan.service
                or snapshot != saved.search
            ):
                raise PermissionError(
                    "Navigation verification changed original guard/snapshot"
                )
            return
        self.state.verify(service, phase, snapshot, control)
