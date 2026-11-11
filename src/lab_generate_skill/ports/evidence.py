"""Evidence persistence contract, independent of filesystem or archive layout.

Every call receives the original bound control; no unbounded default/fallback.
Synchronous FileEvidenceStore is a worker-internal primitive, not this port.
The selected adapter must supervise actual I/O and retain uncertain commits.

put is idempotent for identical bytes; existing different bytes are never
overwritten. read verifies both size and digest, raising domain EvidenceError
for missing/corrupt objects. Metadata is provenance, not authentication.
put validates bytes and complete metadata before persistence. A failed put may
have committed: reconcile the same bytes, never overwrite or assume absence.
When persistence and cleanup both fail, the adapter preserves the primary error
and all cleanup errors separately (filesystem uses BaseExceptionGroup, primary
first). Invalid inputs have no write effects; unsupported payload/metadata types
raise TypeError, invalid metadata fields raise ValidationError.
"""

from typing import Protocol
from lab_generate_skill.ports.lifecycle import OperationControl

from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef


class EvidenceReader(Protocol):
    """Read exactly one referenced object; no arbitrary pathname fallback."""

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes: ...


class EvidenceStore(EvidenceReader, Protocol):
    """Store immutable bytes and return their verified, versioned reference."""

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef: ...


class CurrentEvidenceChecks(Protocol):
    def check_current(self, control: OperationControl) -> None:
        """Check live storage/owner/revocation state; never an immutable-body proof."""
        ...
