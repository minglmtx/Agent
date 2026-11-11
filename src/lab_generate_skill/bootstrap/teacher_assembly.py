"""Default original Teacher assembly and existing Teacher port composition.

Only this root knows the existing actual-wire validator and plan store. No new
runner, ledger, missing-source fallback or default permission.
"""

from lab_generate_skill.application.teacher_assembly import TeacherAssemblyDeps
from lab_generate_skill.application.teacher_assembly_review import (
    TeacherAssemblyReviewDeps,
    review_teacher_assembly,
)
from lab_generate_skill.application.teacher_source_review import TeacherSourceReviewDeps
from lab_generate_skill.application.context_review import ContextReviewDeps
from lab_generate_skill.application.teacher_revision import RecordedTeacher
from lab_generate_skill.application.teacher_send_admission import (
    ConstructionTeacherSendAuthority,
    TeacherSendAdmissionDeps,
)
from lab_generate_skill.domain.teacher_assembly import PublishedTeacherRevisionAssembly
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.ports.teacher_assembly import TeacherAssemblyAuthority
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.evidence import EvidenceReader, EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.requests import RequestLedger
from lab_generate_skill.ports.model import ModelTransport, ModelSendAuthority
from lab_generate_skill.ports.context_projection import (
    ContextPreparationAuthority,
    ContextCountEvidenceVerifier,
)
from lab_generate_skill.adapters.models.teacher_request_binding import (
    verify_teacher_wire_parameters,
)
from lab_generate_skill.adapters.plans.teacher_revision import (
    EvidenceTeacherRevisionPlans,
)
from .teacher_revision import recorded_teacher


def teacher_assembly_dependencies(
    evidence: EvidenceStore,
    journal: ConstructionJournal,
    source: TeacherSourceReviewDeps,
    context: ContextReviewDeps,
    authority: TeacherAssemblyAuthority,
    *,
    plans: RunPlans,
) -> TeacherAssemblyDeps:
    if authority is None or source.authority is None or context.authority is None:
        raise ValueError("Original source/claim/model/fee/count authorities required")
    return TeacherAssemblyDeps(
        evidence,
        journal,
        plans,
        source,
        context,
        authority,
        verify_teacher_wire_parameters,
    )


def teacher_assembly_review_dependencies(
    evidence: EvidenceReader,
    journal: ConstructionJournal,
    source: TeacherSourceReviewDeps,
    context: ContextReviewDeps,
    authority: TeacherAssemblyAuthority,
    *,
    plans: RunPlans,
) -> TeacherAssemblyReviewDeps:
    if authority is None or source.authority is None or context.authority is None:
        raise ValueError("Original recorded source/model/fee authorities required")
    return TeacherAssemblyReviewDeps(
        evidence,
        journal,
        plans,
        source,
        context,
        authority,
        verify_teacher_wire_parameters,
    )


def assembled_teacher(
    published: PublishedTeacherRevisionAssembly,
    review: TeacherAssemblyReviewDeps,
    policy: ContextProjectionPolicy,
    *,
    ledger: RequestLedger,
    transport: ModelTransport,
    evidence: EvidenceStore,
    controls: OperationControls,
    source_authority: ModelSendAuthority,
    context_authority: ContextPreparationAuthority,
    counts: ContextCountEvidenceVerifier,
    runs: RunJournal,
    claims: SourceClaims,
) -> RecordedTeacher:
    """Review original registration before returning the original Teacher object."""
    if policy != published.bound.plan.preparation.policy:
        raise ValueError("Assembled Teacher changed original frozen context policy")
    op = published.bound.plan.send.operation
    review_teacher_assembly(published, review, op, control=controls.bind(op))
    plans = EvidenceTeacherRevisionPlans(
        {published.bound.plan.revision.request_id: published.bound.reference}, evidence
    )
    run = review.journal.read(op).plan.run
    authority = ConstructionTeacherSendAuthority(
        run,
        plans,
        TeacherSendAdmissionDeps(
            review.journal, runs, claims, review.plans, ledger, source_authority
        ),
        controls,
    )
    return recorded_teacher(
        plans,
        policy,
        ledger=ledger,
        transport=transport,
        evidence=evidence,
        controls=controls,
        source_authority=authority,
        context_authority=context_authority,
        counts=counts,
    )
