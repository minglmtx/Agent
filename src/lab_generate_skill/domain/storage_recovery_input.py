"""Original durable inspection input; no retry, termination or takeover permission.

A new process combines the original journal with explicitly supplied frozen
configuration. All bindings are revalidated; it does not discover "latest"
configuration or reconstruct the lost payload. The original command digest is
retained as a fact, not claimed recomputed without its request bytes.
"""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract, Identifier
from .errors import EvidenceNotFound, OwnershipConflict
from .evidence_io import EvidenceCommand
from .evidence_sessions import EvidenceOperationIntent
from .evidence_session_state import EvidenceSessionSnapshot
from .evidence_storage import EvidenceStorageConfig


class StorageRecoveryInput(Contract):
    schema_version: Literal["storage-recovery-input/1"] = "storage-recovery-input/1"
    snapshot: EvidenceSessionSnapshot
    config: EvidenceStorageConfig
    exchange_id: Identifier

    @property
    def intent(self) -> EvidenceOperationIntent:
        for entry in self.snapshot.entries:
            if entry.intent.exchange_id == self.exchange_id:
                return entry.intent
        raise EvidenceNotFound("Original storage exchange is missing")

    @property
    def command(self) -> EvidenceCommand:
        return self.intent.command

    @model_validator(mode="after")
    def original(self) -> Self:
        binding, config = self.snapshot.binding, self.config
        if (
            binding.storage_id,
            binding.storage_config_sha256,
            binding.release_id,
            self.snapshot.capacity,
        ) != (
            config.storage_id,
            config.sha256,
            config.installation.manifest.release_id,
            config.capacity,
        ):
            raise OwnershipConflict(
                "Recovery configuration differs from original session"
            )
        command = self.command
        if (command.root, command.max_object_bytes) != (
            config.evidence_root,
            config.max_object_bytes,
        ):
            raise OwnershipConflict(
                "Recovery descriptor differs from frozen original storage"
            )
        return self
