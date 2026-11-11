"""Mandatory original site record and live worker observations; no permission default."""

from typing import Protocol
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_storage_original import SiteStorageOriginal
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from .lifecycle import OperationControl


class SiteAcquisitionReader(Protocol):
    def read(
        self, configuration: SiteWorkerConfiguration, control: OperationControl
    ) -> SiteStorageOriginal: ...


class SiteWorkerGuard(Protocol):
    def observe(self, control: OperationControl) -> ProcessOwnerGuard: ...
