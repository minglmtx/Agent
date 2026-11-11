"""Bridge a completed original task into the existing allowed Teacher producer."""

from dataclasses import dataclass
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.task_teacher import (
    TaskTeacherInput,
    TaskTeacherReceipt,
    PublishedTaskTeacherAttempt,
)
from lab_generate_skill.domain.teacher_attempt import PublishedTeacherAttempt
from lab_generate_skill.ports.lifecycle import OperationControl
from .context_evidence import publish_raw
from .teacher_attempt import TeacherAttemptDeps, publish_teacher_attempt
from .task_teacher_inputs import TaskTeacherReadDeps, task_teacher_input


@dataclass(frozen=True)
class TaskTeacherDeps:
    original: TaskTeacherReadDeps
    native: TeacherAttemptDeps

    def __post_init__(self) -> None:
        if self.original.evidence is not self.native.evidence:
            raise ValueError(
                "Original task and native Teacher must use the same controlled CAS"
            )


class TaskTeacherUnconfirmed(RuntimeError):
    def __init__(
        self,
        original: TaskTeacherInput,
        phase: str,
        primary: BaseException,
        part: PublishedTeacherAttempt | None,
        retained: tuple[EvidenceRef, ...],
    ) -> None:
        self.original, self.phase, self.primary = original, phase, primary
        self.part, self.retained = part, retained
        super().__init__(
            "Task/Teacher publication unresolved; preserve original facts, never rerun task"
        )


def publish_task_teacher_attempt(
    original: TaskTeacherInput, deps: TaskTeacherDeps, *, control: OperationControl
) -> PublishedTaskTeacherAttempt:
    original = TaskTeacherInput.model_validate(original)
    part = None
    retained: list[EvidenceRef] = []
    phase = "original_task"
    try:
        source = task_teacher_input(
            original, deps.original, original.operation, control=control
        )
        phase = "native_allowed_part"
        part = publish_teacher_attempt(source, deps.native, control=control)
        phase = "task_lineage"
        receipt = TaskTeacherReceipt(original=original, part=part)
        ref = publish_raw(
            deps.native.evidence,
            receipt.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="task-teacher-receipt/1",
                visibility="private",
                producer="original-task-teacher-bridge",
            ),
            retained,
            control,
        )
        return PublishedTaskTeacherAttempt(receipt_ref=ref, part=part)
    except BaseException as error:
        raise TaskTeacherUnconfirmed(
            original, phase, error, part, tuple(retained)
        ) from error
