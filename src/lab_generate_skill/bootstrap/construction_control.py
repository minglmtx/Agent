"""Assemble the planned construction use case over existing role/lifecycle ports.

No resource start, model load, source default, alternative runner or fee ledger.
Teacher factories must reuse assembled_teacher and the original journal proof.
"""

from lab_generate_skill.application.construct_targets import (
    ConstructionDeps,
    ConstructionReadiness,
)
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.evidence import EvidenceReader, EvidenceStore
from lab_generate_skill.ports.retrieval import RetrievalRecords
from lab_generate_skill.ports.construction import ConstructionSteps
from lab_generate_skill.application.construction_preparation import (
    GenerationPreparationDeps,
)
from lab_generate_skill.adapters.plans.construction_generation import (
    ConstructionGenerationReader,
)
from lab_generate_skill.adapters.plans.construction_retrieval import (
    ConstructionRetrievalReader,
)
from lab_generate_skill.adapters.plans.construction_steps import (
    EvidenceConstructionSteps,
)
from lab_generate_skill.application.construction_task_preparation import (
    ActorPreparationDeps,
)


def construction_control_dependencies(
    journal: ConstructionJournal,
    controls: OperationControls,
    *,
    readiness: ConstructionReadiness | None = None,
) -> ConstructionDeps:
    """Start with only explicitly configured capabilities; caller binds role ports.

    Selected missing roles are rejected before registration; record/observe need
    no new-execution eligibility. No unit authority is ever chosen here.
    """
    if journal is None or controls is None:
        raise ValueError("Original construction journal/operation controls required")
    return ConstructionDeps(journal, controls, readiness=readiness)


def generation_preparation_dependencies(
    construction: ConstructionDeps,
    *,
    evidence: EvidenceStore,
    retrieval: RetrievalRecords,
) -> GenerationPreparationDeps:
    return GenerationPreparationDeps(
        construction,
        evidence,
        ConstructionGenerationReader(
            evidence, ConstructionRetrievalReader(evidence, retrieval)
        ),
    )


def construction_steps(evidence: EvidenceReader) -> ConstructionSteps:
    return EvidenceConstructionSteps(evidence)


def actor_preparation_dependencies(
    construction: ConstructionDeps, *, evidence: EvidenceStore
) -> ActorPreparationDeps:
    return ActorPreparationDeps(construction, evidence)
