"""Bind one original execution and role-specific full-file/checkpoint authority."""

from pathlib import Path
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.training_output import (
    TrainingExecution,
    TrainingOutputAuthority,
)
from lab_generate_skill.adapters.training.output_store import SFTOutputStore
from lab_generate_skill.adapters.training.recorded_runtime import (
    RecordedTrainingRuntime,
)


def training_output_runtime(
    workspace: Path,
    publication_root: Path,
    evidence: EvidenceStore,
    *,
    execution: TrainingExecution,
    authority: TrainingOutputAuthority,
    max_files: int,
    max_file_bytes: int,
    max_total_bytes: int,
) -> RecordedTrainingRuntime:
    return RecordedTrainingRuntime(
        workspace,
        publication_root,
        max_files,
        max_file_bytes,
        max_total_bytes,
        execution,
        SFTOutputStore(workspace, evidence, authority),
    )
