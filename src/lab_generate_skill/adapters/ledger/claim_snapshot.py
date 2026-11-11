"""Shared immutable claim decoding; byte transactions retain their own cleanup."""

from pydantic import ValidationError
from lab_generate_skill.domain.claims import (
    SourceClaimKey,
    SourceClaimRecord,
    check_claim_operation,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
)
from lab_generate_skill.adapters.storage.atomic_snapshot import SnapshotTransaction


def decode_claim(raw: bytes, key: SourceClaimKey) -> SourceClaimRecord:
    try:
        record = SourceClaimRecord.model_validate_json(raw)
    except (ValidationError, OwnershipConflict) as error:
        raise EvidenceIntegrityError("Invalid original source claim") from error
    if record.binding.key != key:
        raise OwnershipConflict("Source claim key cannot be rebound")
    return record


def read_claim_record(
    transaction: SnapshotTransaction, key: SourceClaimKey, op: OperationContext
) -> SourceClaimRecord:
    raw = transaction.read()
    if raw is None:
        raise EvidenceNotFound("No committed source claim")
    record = decode_claim(raw, key)
    check_claim_operation(record.binding, op, creating=False)
    transaction.checkpoint()
    return record
