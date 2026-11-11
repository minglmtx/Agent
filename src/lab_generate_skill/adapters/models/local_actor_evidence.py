"""Exact canonical public input and independently retained Actor exchange bytes."""

from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.evidence import EvidenceStore, EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.verified_evidence import VerifiedEvidenceInputs
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody
from lab_generate_skill.policies.evidence_bytes import require_complete_read_bound

T = TypeVar("T", bound=Contract)


class ActorEvidence:
    def __init__(
        self, store: EvidenceStore, *, inputs: EvidenceReader | None = None
    ) -> None:
        self.store = store
        self.inputs = store if inputs is None else inputs

    def read(
        self,
        ref: EvidenceRef,
        schema: str,
        model: type[T],
        limit: int,
        control: OperationControl,
    ) -> T:
        private_state_ref(ref, schema)
        require_complete_read_bound(ref, limit)
        control.checkpoint()
        if isinstance(self.inputs, VerifiedEvidenceInputs):
            value = self.inputs.read_document(
                ref, model, limit, control, canonical=True
            )
            if type(value) is not model:
                raise EvidenceIntegrityError("Actor input changed its exact model")
        else:
            raw = self.raw(ref, limit, control)
            value = model.model_validate_json(raw)
            if value.model_dump_json().encode() != raw:
                raise EvidenceIntegrityError("Actor evidence must be canonical")
        control.checkpoint()
        return value

    def raw(self, ref: EvidenceRef, limit: int, control: OperationControl) -> bytes:
        require_complete_read_bound(ref, limit)
        control.checkpoint()
        body = (
            self.inputs.read_verified(ref, control)
            if isinstance(self.inputs, VerifiedEvidenceInputs)
            else VerifiedEvidenceBody(ref, self.inputs.read(ref, control))
        )
        if type(body) is not VerifiedEvidenceBody or body.reference != ref:
            raise EvidenceIntegrityError("Actor input changed its complete reference")
        control.checkpoint()
        return body.raw

    def put(
        self,
        raw: bytes,
        schema: str,
        retained: list[EvidenceRef],
        control: OperationControl,
    ) -> EvidenceRef:
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer="fixed-actor-worker",
        )
        expected = evidence_reference(raw, metadata)
        retained.append(expected)
        control.checkpoint()
        actual = self.store.put(raw, metadata, control=control)
        if actual != expected:
            retained.append(actual)
            raise EvidenceIntegrityError(
                "Actor publication returned a foreign reference"
            )
        # Retained candidates are not confirmation of persistence. Verify the
        # exact bytes and preserve both candidate and actual return on failure.
        if self.store.read(actual, control=control) != raw:
            raise EvidenceIntegrityError("Actor publication readback differs")
        control.checkpoint()
        return actual
