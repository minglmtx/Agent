"""Mandatory original search/port/scope and writer admission, no default allow."""

from typing import Protocol, Literal
from lab_generate_skill.ports.lifecycle import OperationControl
from .service_contract import AdminServiceSpec
from .search_contract import AdminSearchSnapshot


class AdminSearchAuthority(Protocol):
    def verify(
        self,
        service: AdminServiceSpec,
        phase: Literal["save", "verify", "preflight", "restore"],
        snapshot: AdminSearchSnapshot | None,
        control: OperationControl,
    ) -> None:
        """Verify precommitted original instance/assets/ports and persisted snapshot.
        Save/restore require no competing browser/CLI/background writers. The
        node-local repository must remain exclusively owned; no formal authority
        or resource closure follows from constructing a snapshot descriptor.
        """
        ...
