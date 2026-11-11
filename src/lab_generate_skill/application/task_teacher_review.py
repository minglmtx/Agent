"""Independent original task/native Teacher lineage review; no writer/composer."""

from dataclasses import dataclass
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_teacher import (
    TaskTeacherReceipt,
    PublishedTaskTeacherAttempt,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from .teacher_actor_reads import canonical
from .teacher_attempt_review import TeacherAttemptReviewDeps, review_teacher_attempt
from .task_teacher_inputs import TaskTeacherReadDeps, task_teacher_input


@dataclass(frozen=True)
class TaskTeacherReviewDeps:
    original: TaskTeacherReadDeps
    native: TeacherAttemptReviewDeps

    def __post_init__(self) -> None:
        if self.original.evidence is not self.native.evidence:
            raise ValueError(
                "Original task and native Teacher review require the same readonly CAS"
            )


def review_task_teacher_attempt(
    published: PublishedTaskTeacherAttempt,
    deps: TaskTeacherReviewDeps,
    operation: OperationContext,
    *,
    control: OperationControl,
) -> TaskTeacherReceipt:
    published = PublishedTaskTeacherAttempt.model_validate(published)
    receipt = canonical(
        published.receipt_ref,
        "task-teacher-receipt/1",
        TaskTeacherReceipt,
        deps.original.evidence,
        control,
        512 * 1024,
    )
    if receipt.part != published.part:
        raise EvidenceIntegrityError(
            "Task/Teacher descriptor changed original native part"
        )
    source = task_teacher_input(
        receipt.original, deps.original, operation, control=control
    )
    reviewed = review_teacher_attempt(
        published.part, deps.native, operation, control=control
    )
    if reviewed.original != source:
        raise EvidenceIntegrityError(
            "Task result and allowed native Teacher provenance differ"
        )
    control.checkpoint()
    return receipt
