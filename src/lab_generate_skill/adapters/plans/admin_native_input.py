"""Bounded private Admin native JSON decoding, with no filesystem access."""

from typing import Any
from lab_generate_skill.domain.evidence import EvidenceRef
from .native_input import MAX_NATIVE_BYTES as MAX_NATIVE_BYTES, decode_native_object


def decode_admin_native(raw: bytes, reference: EvidenceRef) -> dict[str, Any]:
    return decode_native_object(
        raw, reference, content_schema="admin-native-contract/1"
    )
