"""Delegate search operations to the same original admitted product command.

This enforces command/snapshot ownership, not external writer closure. The
parent's mandatory task authority remains responsible for actual admission.
"""

from typing import Literal
from lab_generate_skill.ports.lifecycle import OperationControl
from ..service_contract import AdminServiceSpec
from ..search_contract import AdminSearchSnapshot
from .product_recovery_authority import ProductRecoveryAuthority


class ProductSearchAuthority:
    def __init__(self, original: ProductRecoveryAuthority) -> None:
        self.original = original

    def verify(
        self,
        service: AdminServiceSpec,
        phase: Literal["save", "verify", "preflight", "restore"],
        snapshot: AdminSearchSnapshot | None,
        control: OperationControl,
    ) -> None:
        parent = self.original
        if service != parent.plan.service:
            raise PermissionError("Search changed original product service")
        if phase == "save":
            if snapshot is not None:
                raise PermissionError("Search save cannot replace a snapshot")
            parent.verify(parent.plan, "save", None, control)
        else:
            if parent.snapshot is None or snapshot != parent.snapshot.search:
                raise PermissionError("Search changed original product snapshot")
            parent.verify(parent.plan, "restore", parent.snapshot, control)
