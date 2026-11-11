"""Explicit readonly construction review over original proof/evaluator ports.

No registry/current lookup, unit authority, task runner, sender or fee ledger.
The enclosing process still needs actual release installation/read permission.
"""

from dataclasses import replace
from lab_generate_skill.application.review_run import ReviewDeps, ReviewEvaluator
from lab_generate_skill.application.construction_review_teachers import (
    ReviewTeacherService,
    ConstructionTeacherReviews,
)
from lab_generate_skill.application.teacher_assembly_review import (
    TeacherAssemblyReviewDeps,
)
from lab_generate_skill.application.task_teacher_review import TaskTeacherReviewDeps
from lab_generate_skill.application.task_teacher_source import (
    CompletedTaskTeacherSourceAuthority,
)
from lab_generate_skill.application.teacher_source_admission import (
    ConstructionTeacherSourceAuthority,
)
from lab_generate_skill.application.teacher_source_authority import (
    RecordedTeacherSourceAuthority,
)
from lab_generate_skill.application.teacher_transaction_review import (
    construction_snapshot_read,
)
from lab_generate_skill.adapters.plans.construction_history import (
    RecordedConstructionHistory,
)
from lab_generate_skill.adapters.plans.construction_evidence import ConstructionEvidence
from lab_generate_skill.adapters.plans.teacher_revision import (
    EvidenceTeacherRevisionPlans,
)
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.review import ReviewPlan, ReviewTeacher
from lab_generate_skill.domain.model_request import check_model_cleanup
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.construction import (
    ConstructionAuthority,
    ConstructionJournal,
)
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.ports.retrieval import RetrievalRecords
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.ports.context_projection import ContextCountEvidenceVerifier
from lab_generate_skill.ports.review import ReviewAuthority
from .teacher_source_admission import qualified_task_teacher_source
from .teacher_source import teacher_source_authority
from .teacher_revision import recorded_teacher_review


def completed_teacher_review_service(
    declared: ReviewTeacher,
    sealed: ConstructionProgress,
    original: TeacherAssemblyReviewDeps,
    *,
    counts: ContextCountEvidenceVerifier,
    controls: OperationControls,
    enclosing: OperationControl,
) -> ReviewTeacherService:
    declared = ReviewTeacher.model_validate(declared)
    sealed = ConstructionProgress.model_validate(sealed)
    check_model_cleanup(
        declared.published.bound.plan.send.operation, declared.operation
    )
    source, context = original.source.authority, original.context.authority
    if (
        not isinstance(source, CompletedTaskTeacherSourceAuthority)
        or not isinstance(source.original, ConstructionTeacherSourceAuthority)
        or not isinstance(context, RecordedTeacherSourceAuthority)
        or context.deps != original.source
    ):
        raise ValueError(
            "Original complete task/Teacher source and recorded context required"
        )
    snapshot = construction_snapshot_read(
        sealed, declared.operation, controls, enclosing
    )
    recorded = qualified_task_teacher_source(
        source.original.run,
        replace(source.original.deps, construction=snapshot),
        source.deps,
        declared.operation,
    )
    authority = teacher_source_authority(
        context.original,
        context.published,
        evidence=original.evidence,
        observations=original.source.observations,
        retrieval=original.source.retrieval,
        authority=recorded,
        operation=declared.operation,
    )
    review = replace(
        original,
        journal=snapshot,
        source=replace(
            original.source, authority=recorded, operation=declared.operation
        ),
        context=replace(original.context, authority=authority),
    )
    bound = declared.published.bound
    verifier = recorded_teacher_review(
        EvidenceTeacherRevisionPlans(
            {bound.plan.revision.request_id: bound.reference}, original.evidence
        ),
        bound.plan.preparation.policy,
        evidence=original.evidence,
        controls=controls,
        context_authority=authority,
        counts=counts,
    )
    return ReviewTeacherService(declared, review, verifier)


def construction_review_dependencies(
    plan: ReviewPlan,
    sealed: ConstructionProgress,
    *,
    evidence: EvidenceReader,
    plans: RunPlans,
    journal: ConstructionJournal,
    recorded_authority: ConstructionAuthority,
    contexts: ContextRecords,
    retrieval: RetrievalRecords,
    claims: SourceClaims,
    tasks: TaskTeacherReviewDeps,
    evaluators: tuple[ReviewEvaluator, ...],
    teachers: tuple[ReviewTeacherService, ...],
    authority: ReviewAuthority,
    controls: OperationControls,
) -> ReviewDeps:
    plan = ReviewPlan.model_validate(plan)
    sealed = ConstructionProgress.model_validate(sealed)
    teacher = ConstructionTeacherReviews(plan, sealed, teachers, controls)
    history = RecordedConstructionHistory(
        ConstructionEvidence(
            evidence, plans, recorded_authority, contexts, retrieval, claims, teacher
        ),
        plan,
        sealed,
        journal,
    )
    return ReviewDeps(
        evidence, plans, history, tasks, contexts, evaluators, authority, controls
    )
