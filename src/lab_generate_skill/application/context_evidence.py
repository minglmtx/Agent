"""Controlled context CAS bytes; preserve uncertain publications, never repair."""

from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader, EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from .verified_evidence_inputs import verified_input_bytes, verified_input_document

T = TypeVar("T", bound=Contract)


def read_bytes(
    store: EvidenceReader, reference: EvidenceRef, limit: int, control: OperationControl
) -> bytes:
    return verified_input_bytes(store, reference, limit, control)


def read_document(
    store: EvidenceReader,
    reference: EvidenceRef,
    model: type[T],
    control: OperationControl,
) -> T:
    if (reference.visibility, reference.content_schema, reference.media_type) != (
        "private",
        "context-preparation/2",
        "application/json",
    ):
        raise EvidenceIntegrityError("Original private preparation metadata required")
    return verified_input_document(store, reference, model, 256 * 1024, control)


def publish_bytes(
    store: EvidenceStore,
    raw: bytes,
    schema: str,
    retained: list[EvidenceRef],
    control: OperationControl,
) -> EvidenceRef:
    metadata = EvidenceMetadata(
        media_type="application/json",
        content_schema=schema,
        visibility="private",
        producer="context-preparation-v2",
    )
    return publish_raw(store, raw, metadata, retained, control)


def publish_raw(
    store: EvidenceStore,
    raw: bytes,
    metadata: EvidenceMetadata,
    retained: list[EvidenceRef],
    control: OperationControl,
) -> EvidenceRef:
    candidate = evidence_reference(raw, metadata)
    retained.append(candidate)
    control.checkpoint()
    actual = EvidenceRef.model_validate(store.put(raw, metadata, control))
    if actual != candidate:
        retained.append(actual)
        raise EvidenceIntegrityError(
            "Context publication returned foreign metadata/reference"
        )
    if read_bytes(store, actual, len(raw), control) != raw:
        raise EvidenceIntegrityError(
            "Context publication readback differs from complete bytes"
        )
    control.checkpoint()
    return actual
