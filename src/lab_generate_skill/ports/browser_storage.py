"""Original browser journal reader and live process guard, never default permission."""

from typing import Protocol
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_storage_original import BrowserStorageOriginal
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from .lifecycle import OperationControl


class BrowserAcquisitionReader(Protocol):
    def read(
        self, configuration: BrowserWorkerConfiguration, control: OperationControl
    ) -> BrowserStorageOriginal: ...


class BrowserStorageGuard(Protocol):
    def observe(self, control: OperationControl) -> ProcessOwnerGuard:
        """Observe the same original process, including its owned transport threads."""
        ...
