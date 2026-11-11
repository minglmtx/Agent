"""Explicit read-only historical composition; no legacy module import."""

from pathlib import Path
from pydantic import TypeAdapter
from lab_generate_skill.adapters.storage.historical_files import read_historical_file
from lab_generate_skill.adapters.storage.historical_reference import (
    WorkspaceHistoricalReader,
)
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.domain.historical_reference import (
    HistoricalReferenceMap,
    HistoricalKey,
)
from lab_generate_skill.domain.validation import Sha256
from lab_generate_skill.ports.historical_reference import HistoricalReader
from lab_generate_skill.ports.lifecycle import OperationControl


def open_historical_reader(
    root: Path, map_name: str, map_sha256: str, control: OperationControl
) -> HistoricalReader:
    digest = TypeAdapter(Sha256).validate_python(map_sha256, strict=True)
    raw = read_historical_file(root, map_name, digest, 16 * 1024 * 1024, control)
    json_object(raw)
    mapping = HistoricalReferenceMap.model_validate_json(raw)
    return WorkspaceHistoricalReader(root, mapping)


def read_historical_reference(
    root: Path, map_name: str, map_sha256: str, key: "HistoricalKey"
) -> bytes:
    """Bounded synchronous composition for the explicit compute-node reader."""
    from datetime import datetime, timedelta, timezone
    from lab_generate_skill.adapters.clock import SystemClock
    from lab_generate_skill.runtime.lifecycle import OperationGuards
    from lab_generate_skill.domain.lifecycle import OperationContext, CancellationRef

    class NoCancellation:
        def is_cancelled(self, reference: CancellationRef) -> bool:
            return False

    op = OperationContext(
        operation_id="historical-read",
        run_id="historical-read",
        owner_id="reader",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
    )
    control = OperationGuards(SystemClock(), NoCancellation()).bind(op)
    reader = open_historical_reader(root, map_name, map_sha256, control)
    return reader.read(key, control)
