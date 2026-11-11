"""Assemble original SFT runtime; mandatory actual phase/resource dependencies."""

from pathlib import Path
from lab_generate_skill.domain.training_resource import TrainingResourceSpec
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControls, Clock
from lab_generate_skill.ports.training import TrainingAuthority
from lab_generate_skill.ports.training_resource import TrainingResourceAuthority
from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from lab_generate_skill.adapters.training.execution import RegisteredTrainingExecution
from lab_generate_skill.adapters.training.closed_authority import (
    ClosedTrainingWorkerAuthority,
)
from lab_generate_skill.adapters.training.native_execution import (
    OriginalTrainingOutputAuthority,
)
from lab_generate_skill.adapters.training.recorded_runtime import (
    RecordedTrainingRuntime,
)
from .training_output import training_output_runtime


def registered_training_runtime(
    spec: TrainingResourceSpec,
    *,
    journal: ResourceJournal,
    evidence: EvidenceStore,
    controls: OperationControls,
    clock: Clock,
    source_authority: TrainingAuthority,
    resource_authority: TrainingResourceAuthority,
    allocation_verifier: SlurmAllocationVerifier,
) -> RecordedTrainingRuntime:
    spec = TrainingResourceSpec.model_validate(spec)
    execution = RegisteredTrainingExecution(
        spec,
        journal=journal,
        evidence=evidence,
        controls=controls,
        clock=clock,
        source_authority=source_authority,
        resource_authority=resource_authority,
        allocation_verifier=allocation_verifier,
    )
    authority = OriginalTrainingOutputAuthority(
        evidence, ClosedTrainingWorkerAuthority(spec, evidence, resource_authority)
    )
    c = spec.configuration.output
    return training_output_runtime(
        Path(c.workspace_root),
        Path(c.publication_root),
        evidence,
        execution=execution,
        authority=authority,
        max_files=c.max_files,
        max_file_bytes=c.max_file_bytes,
        max_total_bytes=c.max_total_bytes,
    )
