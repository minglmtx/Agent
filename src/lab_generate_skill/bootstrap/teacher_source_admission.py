"""Original source/claim/run admission plus existing native leaf/feedback proof."""

from lab_generate_skill.application.teacher_source_admission import (
    ConstructionTeacherSourceAuthority,
    TeacherConstructionSourceDeps,
)
from lab_generate_skill.application.teacher_attempt_authority import (
    NativeTeacherSourceAuthority,
)
from lab_generate_skill.application.teacher_attempt_review import (
    TeacherAttemptReviewDeps,
)
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.teacher_attempt import PublishedTeacherAttempt
from .teacher_attempt import native_teacher_source_authority
from lab_generate_skill.application.task_teacher_review import TaskTeacherReviewDeps
from lab_generate_skill.application.task_teacher_source import (
    CompletedTaskTeacherSourceAuthority,
)


def qualified_native_teacher_source(
    run: RunBinding,
    source: TeacherConstructionSourceDeps,
    parts: tuple[PublishedTeacherAttempt, ...],
    native_review: TeacherAttemptReviewDeps,
    recorded_operation: OperationContext,
) -> NativeTeacherSourceAuthority:
    """Never selects unit authorities or grants model/provider/fee permission."""
    original = ConstructionTeacherSourceAuthority(run, source, recorded_operation)
    return native_teacher_source_authority(
        original, parts, native_review, recorded_operation
    )


def qualified_task_teacher_source(
    run: RunBinding,
    source: TeacherConstructionSourceDeps,
    task_review: TaskTeacherReviewDeps,
    recorded_operation: OperationContext,
) -> CompletedTaskTeacherSourceAuthority:
    """Use original source admission and existing full task/native verification."""
    original = ConstructionTeacherSourceAuthority(run, source, recorded_operation)
    return CompletedTaskTeacherSourceAuthority(
        original, task_review, source.contexts, recorded_operation
    )
