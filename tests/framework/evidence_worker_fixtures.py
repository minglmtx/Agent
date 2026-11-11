"""Independent worker messages for deterministic storage boundary tests."""

from pathlib import Path
from typing import Literal
from lab_generate_skill.domain.evidence_io import EvidenceCommand
from lab_generate_skill.domain.evidence_identity import evidence_reference
from test_filesystem_evidence import metadata


def command(
    root: Path, data: bytes = b"evidence", operation: Literal["put", "read"] = "put"
) -> EvidenceCommand:
    return EvidenceCommand(
        exchange_id="exchange-1",
        operation=operation,
        root=str(root),
        max_object_bytes=max(1, len(data)),
        reference=evidence_reference(data, metadata()),
        metadata=metadata() if operation == "put" else None,
    )
