"""Single-call stable snapshot/birth mechanics, separated from model execution."""

from pathlib import Path
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorBinding,
    LocalGeneratorIntent,
    LocalGeneratorSnapshot,
    invocation_key,
)
from lab_generate_skill.adapters.storage.atomic_snapshot import (
    AtomicSnapshotFile,
    SnapshotTransaction,
)
from lab_generate_skill.adapters.processes.wire_json import json_object


def invocation_file(
    root: Path, binding: LocalGeneratorBinding, request_id: str
) -> AtomicSnapshotFile:
    key = invocation_key(binding, request_id)
    return AtomicSnapshotFile(root, key + ".local-generator.json", max_bytes=32768)


def load_invocation(transaction: SnapshotTransaction) -> LocalGeneratorSnapshot | None:
    raw = transaction.read()
    birth = transaction.pending("0" * 64)
    if raw is None:
        if birth is not None:
            raise EvidenceIntegrityError("Used local inference cannot be recreated")
        return None
    try:
        json_object(raw)
        value = LocalGeneratorSnapshot.model_validate_json(raw)
        if value.model_dump_json().encode() != raw:
            raise ValueError("Noncanonical local inference snapshot")
    except ValueError as error:
        raise EvidenceIntegrityError("Invalid local inference snapshot") from error
    if birth != value.intent.model_dump_json().encode():
        raise EvidenceIntegrityError("Local inference birth record missing or changed")
    return value


def require_intent(
    snapshot: LocalGeneratorSnapshot, intent: LocalGeneratorIntent
) -> None:
    if snapshot.intent != intent:
        raise OwnershipConflict("Original local inference identity or inputs changed")
