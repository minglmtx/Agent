"""Single Teacher port assembly over original CAS/ledger/provider/source gates."""

from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.ports.evidence import EvidenceStore, EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.model import ModelTransport, ModelSendAuthority
from lab_generate_skill.ports.requests import RequestLedger
from lab_generate_skill.ports.context_projection import (
    ContextPreparationAuthority,
    ContextCountEvidenceVerifier,
)
from lab_generate_skill.ports.teacher_revision import TeacherRevisionPlans
from lab_generate_skill.application.context_review import ContextReviewDeps
from lab_generate_skill.application.teacher_revision import RecordedTeacher
from lab_generate_skill.application.teacher_revision_review import (
    RecordedTeacherRevisionReview,
)
from lab_generate_skill.application.teacher_revision_admission import (
    TeacherInputSendAuthority,
)
from lab_generate_skill.adapters.models.paid_sender import LedgerModelSender
from lab_generate_skill.adapters.models.teacher_response import OpenRouterTeacherDecoder
from .context_projection import build_teacher_context


def recorded_teacher(
    plans: TeacherRevisionPlans,
    policy: ContextProjectionPolicy,
    *,
    ledger: RequestLedger,
    transport: ModelTransport,
    evidence: EvidenceStore,
    controls: OperationControls,
    source_authority: ModelSendAuthority,
    context_authority: ContextPreparationAuthority,
    counts: ContextCountEvidenceVerifier,
) -> RecordedTeacher:
    if source_authority is None or context_authority is None or counts is None:
        raise ValueError(
            "Qualified original source/provider/fee and credible count evidence required; no default allow"
        )
    project, protection = build_teacher_context(policy)
    review = ContextReviewDeps(evidence, context_authority, project, protection, counts)
    authority = TeacherInputSendAuthority(source_authority, plans, review, controls)
    sender = LedgerModelSender(ledger, transport, evidence, controls, authority)
    return RecordedTeacher(
        plans, sender, evidence, controls, review, OpenRouterTeacherDecoder()
    )


def recorded_teacher_review(
    plans: TeacherRevisionPlans,
    policy: ContextProjectionPolicy,
    *,
    evidence: EvidenceReader,
    controls: OperationControls,
    context_authority: ContextPreparationAuthority,
    counts: ContextCountEvidenceVerifier,
) -> RecordedTeacherRevisionReview:
    if context_authority is None or counts is None:
        raise ValueError(
            "Original readonly source and count proof verification required"
        )
    project, protection = build_teacher_context(policy)
    return RecordedTeacherRevisionReview(
        plans,
        evidence,
        controls,
        ContextReviewDeps(evidence, context_authority, project, protection, counts),
        OpenRouterTeacherDecoder(),
    )
