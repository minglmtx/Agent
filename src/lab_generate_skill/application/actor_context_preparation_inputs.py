"""Carry only actually persisted preparation bodies into the same review graph."""

from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from .actor_context_review_inputs import ActorContextReviewInputs


class ActorContextPreparationInputs(ActorContextReviewInputs):
    def __init__(self, original: EvidenceStore) -> None:
        super().__init__(original)
        self._store = original

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        self._open(control)
        expected = evidence_reference(data, metadata)
        actual = self._store.put(data, metadata, control)
        if actual != expected:
            raise EvidenceIntegrityError(
                "Actor preparation publication changed identity"
            )
        # This read must reach the original store, even for a previously retained
        # reference. A local input is never proof that an uncertain write exists.
        body = VerifiedEvidenceBody(actual, self._store.read(actual, control))
        if body.raw != data:
            raise EvidenceIntegrityError(
                "Actor preparation publication readback changed"
            )
        self.retain(body, control)
        self._open(control)
        return actual
