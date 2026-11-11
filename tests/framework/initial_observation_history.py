"""Read original engineering facts without upgrading their worker contracts.

Historical acceptance remains bound to its original frozen code. This reader
cannot create current InitialObservationSelection or execution permission.
"""

from pathlib import Path
from typing import Any
import hashlib
import json
from lab_generate_skill.domain.errors import EvidenceNotFound
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.lifecycle import ResourceRecord
from lab_generate_skill.ports.lifecycle import OperationControl
from evidence_control_fixtures import EvidenceFixtureStore
from test_slurm_commands import guard

ROOT = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-core-contracts-v1/check-4772266"
)
REPORT = ROOT / "registered-site-prepared_browser.json"
REPORT_SHA = "ff42a8fb01e87684713bfade7307f2ee9bd7cb563c82119b8f3fcd95e2147869"


class ArchiveStore:
    def __init__(self, output: Path) -> None:
        self.original = EvidenceFixtureStore(
            ROOT
            / "tmp/pytest-of-r102bf10/pytest-0/test_registered_actual_site_an0/evidence",
            initialize=False,
        )
        self.output = EvidenceFixtureStore(output)

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        try:
            return self.output.read(reference, control)
        except EvidenceNotFound:
            return self.original.read(reference, control)

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        return self.output.put(data, metadata, control)


def read_archive(
    root: Path,
) -> tuple[dict[str, Any], ArchiveStore, ResourceRecord, ResourceAcquisitionIntent]:
    raw = REPORT.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == REPORT_SHA
    report = json.loads(raw)
    assert report["passed"] and report["private_root_removed"]
    browser = report["prepared_browser"]
    record = ResourceRecord.model_validate_json(json.dumps(browser["browser_record"]))
    assert record.state == "closed"
    assert browser["browser_ending"]["details"]["cleanup_errors"] == []
    assert report["ending"]["details"]["cleanup_errors"] == []
    store = ArchiveStore(root)
    intent = ResourceAcquisitionIntent.model_validate_json(
        store.read(record.events[1].evidence[0], guard())
    )
    return report, store, record, intent
