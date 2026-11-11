"""Bind original source readers and fixed Generator projection; no default rights."""

from collections.abc import Callable
from lab_generate_skill.application.export_targets import ExportDeps
from lab_generate_skill.application.export_inputs import RecordedExportInputs
from lab_generate_skill.application.review_run import ReviewDeps
from lab_generate_skill.domain.review import ReviewPlan
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.export import ExportAuthority
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.retrieval import RetrievalRecords
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.adapters.plans.construction_generation import (
    ConstructionGenerationReader,
)
from lab_generate_skill.adapters.plans.construction_retrieval import (
    ConstructionRetrievalReader,
)
from lab_generate_skill.generator.prompting import prepare_generator


def export_dependencies(
    evidence: EvidenceStore,
    controls: OperationControls,
    *,
    reviews: Callable[[ReviewPlan], ReviewDeps],
    retrieval: RetrievalRecords,
    observations: ObservationLoader,
    authority: ExportAuthority,
) -> ExportDeps:
    return ExportDeps(
        evidence,
        RecordedExportInputs(
            evidence,
            reviews,
            ConstructionGenerationReader(
                evidence, ConstructionRetrievalReader(evidence, retrieval)
            ),
            observations,
            prepare_generator,
        ),
        authority,
        controls,
    )
