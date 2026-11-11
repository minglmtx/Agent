"""Re-read original Actor leaves after closure without a forward composer."""

from dataclasses import dataclass
from lab_generate_skill.domain.teacher_attempt import (
    PublishedTeacherAttempt,
    TeacherAttemptReceipt,
)
from lab_generate_skill.domain.teacher_source import TeacherAttemptView
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.ports.traces import TraceRecords
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.teacher_attempt import (
    TeacherAttemptAuthority,
    TeacherAttemptVerifier,
)
from .teacher_actor_reads import read_actor_material, canonical


@dataclass(frozen=True)
class TeacherAttemptReviewDeps:
    evidence: EvidenceReader
    observations: ObservationLoader
    traces: TraceRecords
    authority: TeacherAttemptAuthority
    verify: TeacherAttemptVerifier


def review_teacher_attempt(
    published: PublishedTeacherAttempt,
    deps: TeacherAttemptReviewDeps,
    operation: OperationContext,
    *,
    control: OperationControl,
) -> TeacherAttemptReceipt:
    published = PublishedTeacherAttempt.model_validate(published)
    receipt = canonical(
        published.receipt_ref,
        "teacher-attempt-source-receipt/1",
        TeacherAttemptReceipt,
        deps.evidence,
        control,
        256 * 1024,
    )
    if receipt.source != published.source:
        raise EvidenceIntegrityError("Native attempt receipt changed original source")
    material = read_actor_material(
        receipt.original,
        deps.evidence,
        deps.observations,
        deps.traces,
        operation,
        control=control,
    )
    deps.authority.verify_allowed(
        receipt.original,
        material.request,
        material.trace,
        material.evaluation,
        control=control,
    )
    # This is deliberately a Teacher-visible view, not a generic private read.
    ref = published.source.allowed_view_ref
    from .context_evidence import read_bytes

    raw = read_bytes(deps.evidence, ref, 64 * 1024**2, control)
    allowed = TeacherAttemptView.model_validate_json(raw)
    if allowed.model_dump_json().encode() != raw:
        raise EvidenceIntegrityError(
            "Native attempt view changed canonical complete bytes"
        )
    if (allowed.attempt_id, allowed.candidate_slot) != (
        published.source.attempt_id,
        published.source.candidate_slot,
    ):
        raise EvidenceIntegrityError(
            "Native attempt descriptor changed the original allowed view identity"
        )
    deps.verify(material, allowed)
    control.checkpoint()
    return receipt
