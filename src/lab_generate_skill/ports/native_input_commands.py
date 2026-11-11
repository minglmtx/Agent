"""Fixed native readers receiving private selectors only through bounded stdin.

Only stdout of a completely reaped successful command is returned. Failure
retains the original process capture and must not trigger another invocation.
The enclosing original supervised site resource remains mandatory.
"""

from typing import Protocol
from .lifecycle import OperationControl

MAX_NATIVE_INPUT_BYTES = 8192


class NativeInputCommands(Protocol):
    def run_input(
        self, argv: tuple[str, ...], data: bytes, control: OperationControl
    ) -> bytes: ...
