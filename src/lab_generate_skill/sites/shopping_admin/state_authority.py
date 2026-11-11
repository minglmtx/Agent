"""Required worker-local delegated permission; never a default allow policy."""

from typing import Protocol, Literal
from lab_generate_skill.ports.lifecycle import OperationControl
from .state_contract import AdminStatePlan, AdminStateSnapshot


class AdminStateAuthority(Protocol):
    def verify(
        self,
        plan: AdminStatePlan,
        phase: Literal["save", "restore"],
        snapshot: AdminStateSnapshot | None,
        control: OperationControl,
    ) -> None:
        """Verify original instance/assets, precommitted scope and no other writer.

        Restore also requires original persisted snapshot and task/browser closure.
        Neither this protocol nor a successful leaf reset proves search/external
        state coverage, descendant termination or independent recovery permission.
        """
        ...
