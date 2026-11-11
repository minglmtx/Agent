"""Fresh terminal proof and namespace checks; neither dispatches nor restores."""

from typing import Protocol
from lab_generate_skill.domain.terminal_read import (
    TerminalReadRequest,
    TerminalReadBodies,
)
from .lifecycle import OperationControl


class TerminalEvidenceReads(Protocol):
    def read(
        self, request: TerminalReadRequest, control: OperationControl
    ) -> TerminalReadBodies: ...
    def check_current(self, control: OperationControl) -> None: ...
