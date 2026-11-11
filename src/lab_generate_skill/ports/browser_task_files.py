"""Worker-local file delivery, independent from native browser and judging."""

from typing import Protocol
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from .lifecycle import OperationControl


class BrowserTaskFiles(Protocol):
    def prepare(self, spec: BrowserSessionSpec, control: OperationControl) -> None: ...
    def validate(self, action: BrowserAction, control: OperationControl) -> None: ...
    def close(self, control: OperationControl) -> None: ...
