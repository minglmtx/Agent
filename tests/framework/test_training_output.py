"""Full native-format files -> small reference -> independent original replay."""

import hashlib
from pathlib import Path
from dataclasses import replace
from typing import Any
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.training.recorded_runtime import (
    RecordedTrainingRuntime,
)
from lab_generate_skill.application.train_sft import train_sft
from lab_generate_skill.bootstrap.training import training_dependencies
from training_entry_fixtures import training_case, TrainingCase, UnitTrainingAuthority
from training_output_fixtures import output_case, OutputCase, write_native_format
from lab_generate_skill.domain.training import TrainingPlan, TrainingRunResult
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.ports.lifecycle import OperationControl


class UnitFileExecution:
    def __init__(self, c: OutputCase) -> None:
        self.c = c
        self.calls: list[str] = []

    def verify(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert plan == self.c.plan.training and output == Path(self.c.plan.output_root)
        self.calls.append("verify")

    def execute(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        contract: dict[str, Any],
        control: OperationControl,
    ) -> EvidenceRef:
        self.calls.append("execute-unit-native-format-no-model")
        write_native_format(self.c.plan, data)
        return self.c.returned()

    def close(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        control: OperationControl,
    ) -> ClosureReceipt:
        control.checkpoint()
        self.calls.append("close-unit-proof-only")
        return self.c.closure

    def abort(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        primary: BaseException,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls.append("abort")


def test_native_full_snapshot_reference_and_current_training_consumer_without_models(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = output_case(training_case, "main", create_files=False)
    execution = UnitFileExecution(c)
    snapshots = c.checkpoints()
    runtime = RecordedTrainingRuntime(
        c.workspace,
        Path(c.plan.publication_root),
        128,
        128 * 1024**2,
        512 * 1024**2,
        execution,
        snapshots,
    )
    data_deps = replace(training_case.export.deps, evidence=c.store)
    monkeypatch.setattr(
        "lab_generate_skill.application.train_sft.load_dataset", lambda p, d: c.data
    )
    authority = UnitTrainingAuthority()
    deps = training_dependencies(
        data_deps,
        authority=authority,
        runtime=runtime,
        output_root=c.workspace,
        clock=SystemClock(),
    )
    result = train_sft(c.plan.training, deps)
    assert result.result.status == "completed" and result.result.optimizer_steps == 1
    assert execution.calls == [
        "verify",
        "execute-unit-native-format-no-model",
        "close-unit-proof-only",
    ]
    snapshot = snapshots.read(result.result.checkpoint_ref, c.data, c.control())
    assert snapshot.native.selected_checkpoint == "checkpoint-000001"
    assert (
        snapshot.execution_ref == runtime.execution_ref
        and snapshot.closure == c.closure
    )
    assert snapshot.source.files == snapshot.artifact.files
    for f in snapshot.artifact.files:
        assert (
            hashlib.sha256(
                (Path(snapshot.artifact.root) / f.path).read_bytes()
            ).hexdigest()
            == f.sha256
        )
    assert max(c.store.put_sizes) < 8 * 1024**2
