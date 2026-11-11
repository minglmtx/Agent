"""Consume complete immutable input values; retain ordinary-reader validation."""

from typing import TypeVar
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.verified_evidence import VerifiedEvidenceInputs
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_read_bound

T = TypeVar("T", bound=Contract)


def verified_input_bytes(
    reader: EvidenceReader,
    reference: EvidenceRef,
    limit: int,
    control: OperationControl,
) -> bytes:
    require_complete_read_bound(reference, limit)
    control.checkpoint()
    body = (
        reader.read_verified(reference, control)
        if isinstance(reader, VerifiedEvidenceInputs)
        else VerifiedEvidenceBody(reference, reader.read(reference, control))
    )
    if type(body) is not VerifiedEvidenceBody or body.reference != reference:
        raise EvidenceIntegrityError("Verified input changed its complete reference")
    control.checkpoint()
    return body.raw


def verified_input_document(
    reader: EvidenceReader,
    reference: EvidenceRef,
    model: type[T],
    limit: int,
    control: OperationControl,
    *,
    canonical: bool = True,
) -> T:
    require_complete_read_bound(reference, limit)
    control.checkpoint()
    if isinstance(reader, VerifiedEvidenceInputs):
        value = reader.read_document(
            reference, model, limit, control, canonical=canonical
        )
        if type(value) is not model:
            raise EvidenceIntegrityError("Canonical input changed its exact model")
    else:
        raw = verified_input_bytes(reader, reference, limit, control)
        value = model.model_validate_json(raw)
        if canonical and value.model_dump_json().encode() != raw:
            raise EvidenceIntegrityError("Canonical complete input required")
    control.checkpoint()
    return value
