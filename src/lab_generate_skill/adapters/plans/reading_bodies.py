"""One readonly call's published bytes handed to its original verifier."""

from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl


class PublishedReadingBodies:
    def __init__(self, original: EvidenceStore) -> None:
        self.original = original
        self._bodies: dict[EvidenceRef, VerifiedEvidenceBody] = {}
        self._closed = False

    def begin(self) -> None:
        if self._closed:
            raise OwnershipConflict("Original reading publication lifetime closed")
        self._bodies.clear()

    def clear(self) -> None:
        self._closed = True
        self._bodies.clear()

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        if self._closed:
            raise OwnershipConflict("Reading bodies left original lifetime")
        body = self._bodies.get(reference)
        return self.original.read(reference, control) if body is None else body.raw

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        control.checkpoint()
        if self._closed:
            raise OwnershipConflict("Reading publication lifetime closed")
        expected = evidence_reference(data, metadata)
        reference = self.original.put(data, metadata, control)
        if reference.model_dump(exclude={"uri"}) != expected.model_dump(
            exclude={"uri"}
        ):
            raise EvidenceIntegrityError(
                "Original reading publication changed bytes/metadata"
            )
        body = VerifiedEvidenceBody(reference, data)
        if (
            len(self._bodies) >= 64
            or sum(len(item.raw) for item in self._bodies.values()) + len(data)
            > 16 * 1024**2
        ):
            raise EvidenceIntegrityError(
                "Single readonly return graph exceeds original bounded handoff"
            )
        self._bodies[reference] = body
        control.checkpoint()
        return reference
