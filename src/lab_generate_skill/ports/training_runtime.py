"""Concrete SFT runtime facts/permissions, separate from data phase admission."""

from pathlib import Path
from typing import Protocol, Any
from lab_generate_skill.domain.training import TrainingPlan, TrainingRunResult
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.ports.lifecycle import OperationControl


class TrainingRuntime(Protocol):
    def execute(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        contract: dict[str, Any],
        control: OperationControl,
    ) -> None:
        """Dispatch the original core only in its once-registered supervised worker.

        Parent never loads a tokenizer/model. Worker reconstructs the single
        common input assembly and verifies exact original contract/bytes. No
        alternate attempt, fallback inline execution or automatic retry.
        """
        ...

    def verify(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        control: OperationControl,
    ) -> None:
        """Actual installed code/model/Slurm/GPU, original writer/output and resume rights.

        Worker must be externally supervised; checkpoint filesystem primitives
        run only in that worker. No inferred permission from root/path names.
        """
        ...

    def finish(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        contract: dict[str, Any],
        control: OperationControl,
    ) -> TrainingRunResult:
        """Read original durable summary/checkpoint and runtime evidence, no rerun.

        Must verify complete bytes/lineage and own required physical cleanup;
        errors retain all original output/checkpoint paths and cleanup facts.
        """
        ...

    def abort(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        primary: BaseException,
        control: OperationControl,
    ) -> None:
        """Attempt original owned-resource cleanup after any partial admission/run failure.

        Never create a new worker, overwrite a checkpoint or signal foreign/unknown
        resources. Retain original error, incomplete outputs and cleanup evidence.
        """
        ...
