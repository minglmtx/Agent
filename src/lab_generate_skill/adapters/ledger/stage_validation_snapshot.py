"""Read the unchanged canonical parent while holding its existing claim lock."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.plans.claim_evidence import MAX_CLAIM_BYTES
from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile


@contextmanager
def checked_validation_parent(
    root: Path, validation: SourceStageValidation, control: OperationControl
) -> Iterator[None]:
    validation = SourceStageValidation.model_validate(validation)
    parent = validation.parent
    file = AtomicSnapshotFile(
        root, parent.record.binding.key.filename, max_bytes=MAX_CLAIM_BYTES
    )
    # Validation always locks child -> parent. Ordinary claims never lock a child.
    # Neither a missing parent nor a missing original lock is initialized here.
    with file.locked(control, create_lock=False) as transaction:
        if transaction.read() != parent.record.model_dump_json().encode():
            raise EvidenceIntegrityError(
                "Validation parent differs from canonical durable ownership"
            )
        yield
        transaction.checkpoint()
