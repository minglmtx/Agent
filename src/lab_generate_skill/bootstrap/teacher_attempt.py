"""Native Actor-to-Teacher source composition; no default permission or sender."""

from lab_generate_skill.application.teacher_attempt import TeacherAttemptDeps
from lab_generate_skill.application.teacher_attempt_review import (
    TeacherAttemptReviewDeps,
)
from lab_generate_skill.application.teacher_attempt_authority import (
    NativeTeacherSourceAuthority,
)
from lab_generate_skill.domain.teacher_attempt import PublishedTeacherAttempt
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.evidence import EvidenceStore, EvidenceReader
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.ports.traces import TraceRecords
from lab_generate_skill.ports.teacher_attempt import TeacherAttemptAuthority
from lab_generate_skill.ports.teacher_source import TeacherSourceAuthority
from lab_generate_skill.teacher.actor_attempt import actor_attempt
from lab_generate_skill.teacher.actor_attempt_review import verify_actor_attempt


def native_teacher_attempt(
    evidence: EvidenceStore,
    observations: ObservationLoader,
    traces: TraceRecords,
    authority: TeacherAttemptAuthority,
) -> TeacherAttemptDeps:
    if authority is None:
        raise ValueError("Actual original raw source/feedback authority required")
    return TeacherAttemptDeps(
        evidence, observations, traces, authority, actor_attempt, verify_actor_attempt
    )


def native_teacher_attempt_review(
    evidence: EvidenceReader,
    observations: ObservationLoader,
    traces: TraceRecords,
    authority: TeacherAttemptAuthority,
) -> TeacherAttemptReviewDeps:
    if authority is None:
        raise ValueError("Actual original raw source/feedback authority required")
    return TeacherAttemptReviewDeps(
        evidence, observations, traces, authority, verify_actor_attempt
    )


def native_teacher_source_authority(
    original: TeacherSourceAuthority,
    parts: tuple[PublishedTeacherAttempt, ...],
    deps: TeacherAttemptReviewDeps,
    recorded_operation: OperationContext,
) -> NativeTeacherSourceAuthority:
    return NativeTeacherSourceAuthority(original, parts, deps, recorded_operation)
