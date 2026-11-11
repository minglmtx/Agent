"""Verify actual rendered bytes and full audit independently of projection."""

from lab_generate_skill.domain.teacher_input import (
    AllowedTeacherEvidence,
    TeacherModelInput,
    native_evidence,
)
from lab_generate_skill.domain.teacher_projection import TeacherProjectionPayload
from lab_generate_skill.domain.context_preparation import ContextInputDraft
from lab_generate_skill.domain.context_projection import (
    AllowedContextSource,
    ContextProjectionPolicy,
    ContextProtectionCheck,
    ProjectionKind,
)
from lab_generate_skill.domain.context_transformation import (
    ContextChange,
    ContextTransformAudit,
    context_bytes_sha,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from .context_source import checked_teacher_policy, teacher_source
from .instructions import teacher_projection_guide
from .protection_pages import CompletePageBindings, layout_change
from .protection_events import complete_events


def teacher_audit(
    source: AllowedContextSource,
    allowed: AllowedTeacherEvidence,
    policy: ContextProjectionPolicy,
    kind: ProjectionKind,
    actual: TeacherModelInput,
) -> ContextTransformAudit:
    actual = TeacherModelInput.model_validate(actual)
    changes: tuple[ContextChange, ...] = ()
    if kind == "identity":
        if actual.messages != allowed.messages:
            raise EvidenceIntegrityError(
                "Teacher identity changed original full messages"
            )
    elif kind == "exact_body_sharing":
        if actual.messages[0].content != allowed.messages[
            0
        ].content + teacher_projection_guide(
            native_evidence(allowed.messages[1].content)
        ):
            raise EvidenceIntegrityError(
                "Teacher changed task/template/instruction framing"
            )
        raw = actual.messages[1].content
        payload = TeacherProjectionPayload.model_validate_json(raw)
        if payload.model_dump_json() != raw:
            raise EvidenceIntegrityError(
                "Teacher actual field/body view must use explicit canonical format"
            )
        original = native_evidence(allowed.messages[1].content)
        changes = (
            layout_change(
                "/messages/0/content",
                "/messages/0/content",
                allowed.messages[0].content,
                actual.messages[0].content,
                "EXPLICIT_COMPLETE_TEACHER_GUIDE",
            ),
            layout_change(
                "/messages/1/content",
                "/messages/1/content",
                original,
                payload.model_dump(mode="json"),
                "COMPLETE_NATIVE_FIELD_LAYOUT",
            ),
        ) + complete_events(original, payload, CompletePageBindings(payload.pages))
    else:
        raise ValueError("Unsupported Teacher content transform")
    return ContextTransformAudit(
        role="teacher",
        source_ref=source.original_ref,
        policy_sha256=policy.digest,
        kind=kind,
        input_sha256=context_bytes_sha(actual.model_dump_json().encode()),
        no_op_reason="identity" if not changes else None,
        changes=changes,
    )


class TeacherContextProtection:
    def __init__(self, policy: ContextProjectionPolicy) -> None:
        self.policy = checked_teacher_policy(policy)

    def verify(
        self,
        source: AllowedContextSource,
        original: bytes,
        draft: ContextInputDraft,
        policy: ContextProjectionPolicy,
    ) -> tuple[ContextProtectionCheck, ...]:
        policy = checked_teacher_policy(policy)
        if policy != self.policy:
            raise OwnershipConflict("Teacher protection changed frozen strategy")
        allowed = teacher_source(source, original, policy)
        draft = ContextInputDraft.model_validate(draft)
        valid = (
            draft.source == source
            and draft.policy_sha256 == policy.digest
            and draft.kind in policy.candidate_order
        )
        try:
            actual = TeacherModelInput.model_validate_json(draft.input_bytes)
            if actual.model_dump_json().encode() != draft.input_bytes:
                raise EvidenceIntegrityError(
                    "Teacher model input changed canonical actual bytes"
                )
            audit = teacher_audit(source, allowed, policy, draft.kind, actual)
            valid = valid and audit == draft.audit
        except (ValueError, TypeError, EvidenceIntegrityError):
            valid = False
        return tuple(
            ContextProtectionCheck(
                name=name,
                status="pass" if valid else "fail",
                reason_code=(
                    "COMPLETE_TEACHER_RELATIONS_VERIFIED"
                    if valid
                    else "TEACHER_SOURCE_INPUT_AUDIT_MISMATCH"
                ),
            )
            for name in policy.protected_rules
        )
