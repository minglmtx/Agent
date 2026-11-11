"""Strict allowed role/format/scope binding; never expands Teacher permission."""

from lab_generate_skill.domain.teacher_input import AllowedTeacherEvidence
from lab_generate_skill.domain.context_projection import (
    AllowedContextSource,
    TeacherContextSource,
    ContextProjectionPolicy,
)
from lab_generate_skill.domain.context_transformation import context_bytes_sha
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError

TEACHER_PROTECTION_RULES = (
    "original_allowed_scope",
    "task_template_and_skills",
    "all_candidates_rounds_events",
    "actions_observations_terminal_provenance",
    "complete_original_pages",
    "complete_transform_audit",
)


def checked_teacher_policy(policy: ContextProjectionPolicy) -> ContextProjectionPolicy:
    policy = ContextProjectionPolicy.model_validate(policy)
    if (
        policy.role != "teacher"
        or policy.protected_rules != TEACHER_PROTECTION_RULES
        or any(
            k not in ("identity", "exact_body_sharing") for k in policy.candidate_order
        )
    ):
        raise ValueError(
            "Explicit complete Teacher field/body-sharing contract required"
        )
    return policy


def teacher_source(
    source: AllowedContextSource, original: bytes, policy: ContextProjectionPolicy
) -> AllowedTeacherEvidence:
    if not isinstance(source, TeacherContextSource):
        raise TypeError("Teacher cannot consume an Actor/private source")
    source = TeacherContextSource.model_validate(source)
    checked_teacher_policy(policy)
    if type(original) is not bytes or (len(original), context_bytes_sha(original)) != (
        source.allowed_input_ref.size_bytes,
        source.allowed_input_ref.sha256,
    ):
        raise EvidenceIntegrityError(
            "Teacher source differs from complete original allowed bytes"
        )
    value = AllowedTeacherEvidence.model_validate_json(original)
    if value.model_dump_json().encode() != original:
        raise EvidenceIntegrityError(
            "Teacher allowed input requires explicit canonical format"
        )
    if value.scope != source.scope or value.teacher_round != source.teacher_round:
        raise OwnershipConflict("Teacher changed original task/context/round")
    return value
