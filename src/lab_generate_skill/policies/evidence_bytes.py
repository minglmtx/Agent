"""Pure complete-byte checks shared by application and evidence adapters."""

import hashlib
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError


def require_complete_read_bound(reference: EvidenceRef, limit: int) -> None:
    if type(limit) is not int or not 0 < reference.size_bytes <= limit:
        raise EvidenceIntegrityError("Context evidence exceeds its complete read bound")


def require_complete_bytes(reference: EvidenceRef, raw: bytes) -> None:
    if type(raw) is not bytes or (len(raw), hashlib.sha256(raw).hexdigest()) != (
        reference.size_bytes,
        reference.sha256,
    ):
        raise EvidenceIntegrityError("Context evidence differs from original bytes")
