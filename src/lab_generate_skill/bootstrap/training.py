"""Trusted assembly of existing export consumers and the original SFT adapter."""

from pathlib import Path
from lab_generate_skill.application.train_sft import TrainingDeps
from lab_generate_skill.application.export_targets import ExportDeps
from lab_generate_skill.adapters.training.sft import OriginalSFTTrainer
from lab_generate_skill.ports.lifecycle import Clock
from lab_generate_skill.ports.training import TrainingAuthority
from lab_generate_skill.ports.training_runtime import TrainingRuntime


def training_dependencies(
    dataset: ExportDeps,
    *,
    authority: TrainingAuthority,
    runtime: TrainingRuntime,
    output_root: Path,
    clock: Clock,
) -> TrainingDeps:
    return TrainingDeps(
        dataset,
        authority,
        OriginalSFTTrainer(output_root, runtime, dataset.controls, clock),
        clock,
    )
