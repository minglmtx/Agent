"""Fresh readonly interpreter for synthetic full native files, never a trainer."""

import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from lab_generate_skill.domain.dataset import TrainingExample, DatasetManifest
from lab_generate_skill.domain.export import ExportReceipt
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.training import TrainingPlan
from lab_generate_skill.adapters.training.output_store import SFTOutputStore
from lab_generate_skill.adapters.training.native_execution import (
    OriginalTrainingOutputAuthority,
)
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.ports.lifecycle import OperationControl
from training_output_fixtures import UnitNativeWorkerAuthority
from test_run_journal import CancelSwitch


class ReadOnlyOutputStore:
    def __init__(self, root: Path) -> None:
        self.store = FileEvidenceStore(root, initialize=False)

    def read(self, ref: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        result = self.store.read(ref)
        control.checkpoint()
        return result

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        raise AssertionError("Independent checkpoint replay cannot publish or train")


def main() -> None:
    args = json.loads(Path(sys.argv[1]).read_text())
    assert args["unit_native_fixture_not_weights"] is True
    data = LoadedDataset(
        ExportReceipt.model_validate_json(json.dumps(args["receipt"]).encode()),
        DatasetManifest.model_validate_json(json.dumps(args["manifest"]).encode()),
        tuple(
            TrainingExample.model_validate_json(json.dumps(e).encode())
            for e in args["examples"]
        ),
        "sft",
    )
    plan = TrainingPlan.model_validate_json(json.dumps(args["training"]).encode())
    ref = EvidenceRef.model_validate_json(json.dumps(args["reference"]).encode())
    workspace = Path(args["workspace"])
    evidence = ReadOnlyOutputStore(workspace / "evidence")
    authority = OriginalTrainingOutputAuthority(
        evidence, UnitNativeWorkerAuthority(workspace)
    )
    reader = SFTOutputStore(workspace, evidence, authority)
    controls = OperationGuards(SystemClock(), CancelSwitch())
    operation = plan.cleanup("result", datetime.now(timezone.utc))
    snapshot = reader.read(ref, data, controls.bind(operation))
    Path(sys.argv[2]).write_text(snapshot.model_dump_json())
    print(
        json.dumps(
            dict(
                pid=os.getpid(),
                status=snapshot.native.status,
                complete_files=len(snapshot.artifact.files),
                complete_bytes=sum(e.size_bytes for e in snapshot.artifact.files),
                unit_native_fixture_not_weights=True,
            )
        )
    )


if __name__ == "__main__":
    main()
