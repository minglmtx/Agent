"""In-process immutable complete bytes, never a permission or persistence receipt."""

from dataclasses import dataclass
import hashlib
from .evidence import EvidenceRef
from .errors import EvidenceIntegrityError


@dataclass(frozen=True, slots=True)
class VerifiedEvidenceBody:
    reference: EvidenceRef
    raw: bytes

    def __post_init__(self) -> None:
        reference = EvidenceRef.model_validate(self.reference)
        if type(self.raw) is not bytes or (
            len(self.raw),
            hashlib.sha256(self.raw).hexdigest(),
        ) != (reference.size_bytes, reference.sha256):
            raise EvidenceIntegrityError("Complete immutable evidence body required")
        object.__setattr__(self, "reference", reference)
