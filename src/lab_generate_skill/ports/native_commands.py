"""Bounded trusted worker commands, without arbitrary shell or inherited secrets.

Return stdout only after complete zero exit and direct-child reaping. Exceptions
retain command diagnostics and cleanup errors. Not whole-resource closure proof;
callers must run effectful commands inside their registered supervised resource.
"""

from typing import Protocol
from .lifecycle import OperationControl


class NativeCommands(Protocol):
    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes: ...
