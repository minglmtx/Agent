"""Trusted launch admission, separate from a worker's physical verification."""

from typing import Protocol
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.storage_termination import StorageProcessEnd
from .lifecycle import OperationControl


class EvidenceStorageAdmission(Protocol):
    def authorize_storage(
        self,
        binding: EvidenceSessionBinding,
        config: EvidenceStorageConfig,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Verify real run/source/root/release/writer rights before launch.

        Bootstrap fixes the sole scope/root and installed executable. No unit or
        permissive default; source failures cannot downgrade to run. This right
        covers storage only and never grants a task/model dispatch or recovery.
        """
        ...

    def authorize_cleanup(
        self,
        binding: EvidenceSessionBinding,
        config: EvidenceStorageConfig,
        original: OperationContext,
        cleanup: OperationContext,
        ending: StorageProcessEnd | None,
        control: OperationControl,
    ) -> None:
        """Verify original ownership and ending provenance, even after run stop.

        Cleanup is bounded and linked; it never grants new task/model effects.
        Missing ending permits only isolation, not data inspection or reuse.
        """
        ...
