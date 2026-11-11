"""One immutable successful exchange per original durable invocation identity.

Stable snapshot lock and birth record prevent overwrite/history recreation.
Failures may follow commit: publish only the same captured record or inspect it;
never repeat the model call. This store is not an admission or sending permit.
External supervision still bounds filesystem I/O in production.
"""

from pathlib import Path
from lab_generate_skill.domain.generator_execution import GeneratorExecutionRecord
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorIntent,
    LocalGeneratorOutput,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.storage.atomic_snapshot import (
    AtomicSnapshotFile,
    SnapshotTransaction,
)
from lab_generate_skill.adapters.processes.wire_json import json_object
from .generator_execution_evidence import verify_execution


def _load(
    transaction: SnapshotTransaction, intent: LocalGeneratorIntent
) -> GeneratorExecutionRecord | None:
    raw, birth = transaction.read(), transaction.pending("0" * 64)
    if raw is None:
        if birth is not None:
            raise EvidenceIntegrityError("Recorded execution history is missing")
        return None
    try:
        json_object(raw)
        record = GeneratorExecutionRecord.model_validate_json(raw)
    except (ValueError, RecursionError) as error:
        raise EvidenceIntegrityError("Invalid Generator execution record") from error
    if (
        raw != record.model_dump_json().encode()
        or birth != record.intent.model_dump_json().encode()
    ):
        raise EvidenceIntegrityError(
            "Generator execution birth or canonical bytes differ"
        )
    if record.intent != intent:
        raise OwnershipConflict("Generator execution identity differs")
    return record


class FileGeneratorExecutions:
    def __init__(self, root: Path, evidence: EvidenceStore) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or ".." in root.parts:
            raise ValueError("Execution records require a trusted absolute root")
        self._root, self._evidence = root, evidence

    def _file(self, intent: LocalGeneratorIntent) -> AtomicSnapshotFile:
        if self._root.resolve(strict=True) != self._root or not self._root.is_dir():
            raise EvidenceIntegrityError("Execution record root must be canonical")
        return AtomicSnapshotFile(
            self._root, intent.key + ".generator-execution.json", max_bytes=32768
        )

    def output(
        self, record: GeneratorExecutionRecord, control: OperationControl
    ) -> LocalGeneratorOutput:
        return verify_execution(self._evidence, record, control)

    def publish(
        self, record: GeneratorExecutionRecord, control: OperationControl
    ) -> None:
        record = GeneratorExecutionRecord.model_validate(record)
        self.output(record, control)
        raw = record.model_dump_json().encode()
        if len(raw) > 32768:
            raise ValueError("Generator execution record exceeds snapshot bound")
        try:
            with self._file(record.intent).locked(control) as transaction:
                prior = _load(transaction, record.intent)
                if prior is not None:
                    if prior != record:
                        raise OwnershipConflict(
                            "Original Generator reply cannot change"
                        )
                    transaction.confirm()
                else:
                    transaction.retain_pending(
                        "0" * 64, record.intent.model_dump_json().encode()
                    )
                    transaction.write(raw)
        except BaseException as error:
            setattr(error, "generator_execution_candidate", record)
            raise

    def load(
        self, intent: LocalGeneratorIntent, control: OperationControl
    ) -> GeneratorExecutionRecord:
        intent = LocalGeneratorIntent.model_validate(intent)
        with self._file(intent).locked(control, create_lock=False) as transaction:
            record = _load(transaction, intent)
            if record is None:
                raise EvidenceNotFound("No original Generator execution record")
            self.output(record, control)
            return record
