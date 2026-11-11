"""Five-site source assembly over mandatory original permission/record ports."""

from lab_generate_skill.application.teacher_source import TeacherSourceDeps
from lab_generate_skill.application.teacher_source_review import TeacherSourceReviewDeps
from lab_generate_skill.application.teacher_source_authority import (
    RecordedTeacherSourceAuthority,
)
from lab_generate_skill.domain.teacher_source import PublishedTeacherSource
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.teacher_source import TeacherSourceAuthority
from lab_generate_skill.ports.context_projection import ContextPreparationAuthority
from lab_generate_skill.ports.evidence import EvidenceStore, EvidenceReader
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.ports.retrieval import RetrievalRecords
from lab_generate_skill.teacher.construction_messages import construction_messages


def teacher_source_dependencies(
    evidence: EvidenceStore,
    observations: ObservationLoader,
    retrieval: RetrievalRecords,
    authority: TeacherSourceAuthority,
) -> TeacherSourceDeps:
    if authority is None:
        raise ValueError("Actual original trace/feedback source authority required")
    return TeacherSourceDeps(
        evidence, observations, retrieval, authority, construction_messages
    )


def teacher_source_authority(
    original: ContextPreparationAuthority,
    published: PublishedTeacherSource,
    *,
    evidence: EvidenceReader,
    observations: ObservationLoader,
    retrieval: RetrievalRecords,
    authority: TeacherSourceAuthority,
    operation: OperationContext,
) -> RecordedTeacherSourceAuthority:
    return RecordedTeacherSourceAuthority(
        original,
        published,
        TeacherSourceReviewDeps(
            evidence, observations, retrieval, authority, operation
        ),
    )
