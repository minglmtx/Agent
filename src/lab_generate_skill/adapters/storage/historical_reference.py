"""Read exact original versions exclusively from a pinned workspace library."""

from pathlib import Path
from lab_generate_skill.domain.historical_reference import (
    HistoricalKey,
    HistoricalReferenceMap,
)
from lab_generate_skill.domain.errors import EvidenceNotFound
from lab_generate_skill.ports.lifecycle import OperationControl
from .historical_files import read_historical_file


class WorkspaceHistoricalReader:
    def __init__(self, root: Path, mapping: HistoricalReferenceMap) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("Historical library root must be an absolute Path")
        self._root = root
        mapping = HistoricalReferenceMap.model_validate(mapping)
        self._files = {(f.key.original_path, f.key.sha256): f for f in mapping.files}

    def read(self, key: HistoricalKey, control: OperationControl) -> bytes:
        key = HistoricalKey.model_validate(key)
        control.checkpoint()
        record = self._files.get((key.original_path, key.sha256))
        if record is None:
            raise EvidenceNotFound(
                "Exact historical version is not mapped; no latest/old-path fallback"
            )
        return read_historical_file(
            self._root,
            record.relative_path,
            record.key.sha256,
            record.size_bytes,
            control,
            exact_size=record.size_bytes,
        )
