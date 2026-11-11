"""Exact capture evidence publication, shared by site and browser recorders."""

from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl


class CaptureEvidence:
    def __init__(self, store: EvidenceStore, producer: str) -> None:
        self.store, self.producer = store, producer
        self.candidates: list[EvidenceRef] = []

    def put(self, raw: bytes, schema: str, control: OperationControl) -> EvidenceRef:
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer=self.producer,
        )
        candidate = evidence_reference(raw, metadata)
        self.candidates.append(candidate)
        actual = self.store.put(raw, metadata, control=control)
        if actual.model_dump(exclude={"uri"}) != candidate.model_dump(exclude={"uri"}):
            self.candidates.append(actual)
            raise EvidenceIntegrityError(
                "Capture publication changed bytes or metadata"
            )
        if self.store.read(actual, control=control) != raw:
            raise EvidenceIntegrityError("Capture publication readback differs")
        control.checkpoint()
        return actual
