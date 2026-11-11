"""Release candidate dependencies; neither port may activate a default release.

These synchronous operations run inside an externally supervised worker. The
shared control is checked around I/O, not a guarantee against blocked syscalls.
Documents preserve strict original reference/schema checks and immutable CAS
semantics. Files verify the complete frozen manifest, without repairing assets.
"""

from typing import Protocol
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.registration import RegistryManifest
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.ports.lifecycle import OperationControl


class ReleaseDocuments(Protocol):
    def registry(
        self, reference: EvidenceRef, control: OperationControl
    ) -> RegistryManifest: ...

    def manifest(
        self, reference: EvidenceRef, control: OperationControl
    ) -> ReleaseManifest: ...

    def put(self, manifest: ReleaseManifest, control: OperationControl) -> EvidenceRef:
        """Store canonical manifest bytes; failure may follow a committed write."""
        ...


class ReleaseFiles(Protocol):
    def verify(self, manifest: ReleaseManifest, control: OperationControl) -> None:
        """Verify every pinned file in the trusted workspace; raise on failure."""
        ...
