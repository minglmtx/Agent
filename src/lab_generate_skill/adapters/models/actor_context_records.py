"""Bounded exact canonical metadata reads; never inspect a live model/file tree."""

import hashlib
from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.wire_json import json_object

T = TypeVar("T", bound=Contract)


def actor_context_bytes(
    evidence: EvidenceReader,
    reference: EvidenceRef,
    schema: str,
    limit: int,
    control: OperationControl,
) -> bytes:
    reference = EvidenceRef.model_validate(reference)
    if (reference.visibility, reference.content_schema, reference.media_type) != (
        "private",
        schema,
        "application/json",
    ) or not 0 < reference.size_bytes <= limit:
        raise EvidenceIntegrityError("Original bounded private Actor metadata required")
    control.checkpoint()
    raw = evidence.read(reference, control)
    if type(raw) is not bytes or (len(raw), hashlib.sha256(raw).hexdigest()) != (
        reference.size_bytes,
        reference.sha256,
    ):
        raise EvidenceIntegrityError("Actor metadata changed original bytes")
    control.checkpoint()
    json_object(raw)
    return raw


def actor_context_document(
    evidence: EvidenceReader,
    reference: EvidenceRef,
    schema: str,
    model: type[T],
    limit: int,
    control: OperationControl,
) -> T:
    raw = actor_context_bytes(evidence, reference, schema, limit, control)
    value = model.model_validate_json(raw)
    if value.model_dump_json().encode() != raw:
        raise EvidenceIntegrityError("Actor metadata is not original canonical JSON")
    return value
