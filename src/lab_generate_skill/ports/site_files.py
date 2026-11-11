"""One effectful materialization after original resource intent acknowledgement."""

from typing import Protocol
from lab_generate_skill.domain.site_files import SiteFilesPlan
from .lifecycle import OperationControl


class SiteFiles(Protocol):
    def stage(self, plan: SiteFilesPlan, control: OperationControl) -> None:
        """Create only a fresh exact root; pinned read-only image + empty state/logs.

        Any failure retains partial files. Never reuse, overwrite or remove an
        existing root; only the external original resource owner may clean it.
        Synchronous implementation must run in its registered supervised worker.
        """
        ...
