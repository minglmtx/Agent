"""New readonly interpreter for explicit unit resource/wire/full-file proofs.

The original model/kernel/source facts remain synthetic.  This is a reader
test, not a production authority, training grant, or alternative runner.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.adapters.training.closed_authority import (
    ClosedTrainingWorkerAuthority,
)
from lab_generate_skill.adapters.training.native_execution import (
    OriginalTrainingOutputAuthority,
)
from lab_generate_skill.adapters.training.output_store import SFTOutputStore
from lab_generate_skill.adapters.training.worker_data import read_training_data
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.training_resource import TrainingResourceSpec
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_resource_journal import NoCancellation
from training_resource_fixtures import UnitResourceAuthority


class ReadOnlyEvidence:
    def __init__(self, root: Path) -> None:
        self.store = FileEvidenceStore(root, initialize=False)
        self.put_attempts = 0

    def read(self, ref: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        raw = self.store.read(ref)
        control.checkpoint()
        return raw

    def put(
        self, raw: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        self.put_attempts += 1
        raise AssertionError("Fresh resource proof reader cannot publish")


class UnitReadOnlyAuthority(UnitResourceAuthority):
    def _check(self, phase: str, control: OperationControl) -> None:
        assert phase == "read", "Independent reader has no execution/closure grant"
        super()._check(phase, control)


def main() -> None:
    args = json.loads(Path(sys.argv[1]).read_text())
    assert args["unit_model_kernel_and_source_not_real_training"] is True
    spec = TrainingResourceSpec.model_validate_json(json.dumps(args["spec"]))
    assert spec.configuration.output.training.training_id.startswith("unit-sft-")
    ref = EvidenceRef.model_validate(args["reference"])
    workspace = Path(args["workspace"])
    assert Path(spec.configuration.evidence_root) == workspace / "evidence"
    evidence = ReadOnlyEvidence(workspace / "evidence")
    controls = OperationGuards(SystemClock(), NoCancellation())
    op = spec.operation.cleanup(
        "unit-new-process-read", now=datetime.now(timezone.utc), seconds=30
    )
    control = controls.bind(op)
    data = read_training_data(spec.configuration.output.training, evidence, control)
    assert all(e.task.family == "unit-contract-only" for e in data.examples)
    read_authority = UnitReadOnlyAuthority()
    authority = OriginalTrainingOutputAuthority(
        evidence, ClosedTrainingWorkerAuthority(spec, evidence, read_authority)
    )
    snapshot = SFTOutputStore(workspace, evidence, authority).read(ref, data, control)
    assert read_authority.calls and set(read_authority.calls) == {"read"}
    assert evidence.put_attempts == 0
    Path(sys.argv[2]).write_text(snapshot.model_dump_json())
    print(
        json.dumps(
            dict(
                pid=os.getpid(),
                status=snapshot.native.status,
                closure=snapshot.closure.status,
                complete_files=len(snapshot.artifact.files),
                complete_bytes=sum(e.size_bytes for e in snapshot.artifact.files),
                put_attempts=evidence.put_attempts,
                authority_phases=read_authority.calls,
                unit_model_kernel_and_source_not_real_training=True,
            )
        )
    )


if __name__ == "__main__":
    main()
