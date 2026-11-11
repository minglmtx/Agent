"""Independent full source-field review, without composer/tokenizer/writer/send."""

from dataclasses import dataclass
from lab_generate_skill.domain.teacher_source import (
    PublishedTeacherSource,
    TeacherSourceReceipt,
)
from lab_generate_skill.domain.teacher_input import (
    AllowedTeacherEvidence,
    native_evidence,
)
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.teacher_json import same_json
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.ports.retrieval import RetrievalRecords
from lab_generate_skill.ports.teacher_source import TeacherSourceAuthority
from lab_generate_skill.ports.lifecycle import OperationControl
from .context_evidence import read_bytes
from .teacher_source_inputs import read_parts


@dataclass(frozen=True)
class TeacherSourceReviewDeps:
    evidence: EvidenceReader
    observations: ObservationLoader
    retrieval: RetrievalRecords
    authority: TeacherSourceAuthority
    operation: OperationContext


def review_teacher_source(
    published: PublishedTeacherSource,
    deps: TeacherSourceReviewDeps,
    *,
    control: OperationControl,
) -> TeacherSourceReceipt:
    published = PublishedTeacherSource.model_validate(published)
    raw = read_bytes(deps.evidence, published.receipt_ref, 256 * 1024, control)
    receipt = TeacherSourceReceipt.model_validate_json(raw)
    if receipt.model_dump_json().encode() != raw or receipt.source != published.source:
        raise EvidenceIntegrityError(
            "Teacher source receipt changed original published bytes"
        )
    raw = read_bytes(deps.evidence, receipt.progress_ref, 8 * 1024**2, control)
    progress = ConstructionProgress.model_validate_json(raw)
    if progress.model_dump_json().encode() != raw:
        raise EvidenceIntegrityError(
            "Teacher source history must be complete canonical original"
        )
    op = OperationContext.model_validate(deps.operation)
    original = receipt.bindings.operation
    if op != original and not (
        op.mode == "cleanup"
        and op.parent_operation_id == original.operation_id
        and (op.run_id, op.owner_id, op.attempt_id, op.allocation_id, op.recovery_ref)
        == (original.run_id, original.owner_id, None, None, None)
    ):
        raise OwnershipConflict(
            "Source readonly review requires original command or bounded parent cleanup"
        )
    deps.authority.verify_recorded(progress, receipt.bindings, control=control)
    parts = read_parts(
        progress,
        receipt.bindings,
        deps.evidence,
        deps.observations,
        deps.retrieval,
        op,
        control=control,
    )
    raw = read_bytes(
        deps.evidence, receipt.source.allowed_input_ref, 64 * 1024**2, control
    )
    allowed = AllowedTeacherEvidence.model_validate_json(raw)
    if allowed.model_dump_json().encode() != raw or (
        allowed.scope,
        allowed.task,
        allowed.teacher_round,
    ) != (parts.scope, parts.public.task, receipt.bindings.teacher_round):
        raise EvidenceIntegrityError(
            "Teacher allowed source changed original context/task/round"
        )
    text = read_bytes(
        deps.evidence, receipt.bindings.instructions_ref, 256 * 1024, control
    ).decode("utf-8")
    if allowed.messages[0].content != text:
        raise EvidenceIntegrityError(
            "Teacher source changed complete original instructions"
        )
    body = native_evidence(allowed.messages[1].content)
    if set(body) != {
        "task",
        "public_task",
        "initial_observation",
        "retrieved_skills",
        "attempts",
        "best_successful_attempt",
    }:
        raise EvidenceIntegrityError("Teacher construction source fields changed")
    if (
        body["task"] != parts.public.task.goal
        or not same_json(body["public_task"], parts.public.task.model_dump(mode="json"))
        or body["initial_observation"] != parts.initial
    ):
        raise EvidenceIntegrityError(
            "Teacher source changed original public task or initial text"
        )
    if not same_json(
        body["retrieved_skills"], [s.model_payload() for s in parts.skills]
    ) or not same_json(body["attempts"], [a.native for a in parts.attempts]):
        raise EvidenceIntegrityError(
            "Teacher source lost/changed/reordered original attempts or skills"
        )
    if parts.best is None:
        if body["best_successful_attempt"] is not None:
            raise EvidenceIntegrityError("Teacher source invented a successful attempt")
    else:
        best = parts.attempts[parts.best].native
        if not same_json(
            body["best_successful_attempt"],
            {"skill": best["skill"], "steps": best["steps"]},
        ):
            raise EvidenceIntegrityError(
                "Teacher source changed original stable best attempt"
            )
    control.checkpoint()
    return receipt
