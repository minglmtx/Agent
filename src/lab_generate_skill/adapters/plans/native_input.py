"""Bounded private native JSON bytes; schema selection is trusted bootstrap input."""

import hashlib
from typing import Any
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.adapters.processes.wire_json import json_object

MAX_NATIVE_BYTES = 1024 * 1024


def decode_native_object(
    raw: bytes, reference: EvidenceRef, *, content_schema: str
) -> dict[str, Any]:
    reference = EvidenceRef.model_validate(reference)
    if (reference.visibility, reference.content_schema, reference.media_type) != (
        "private",
        content_schema,
        "application/json",
    ):
        raise ValueError("Expected private native-contract reference")
    if (
        type(raw) is not bytes
        or not 1 <= len(raw) <= MAX_NATIVE_BYTES
        or (
            reference.size_bytes != len(raw)
            or reference.sha256 != hashlib.sha256(raw).hexdigest()
        )
    ):
        raise EvidenceIntegrityError(
            "Native contract bytes differ from bounded reference"
        )
    return json_object(raw)
