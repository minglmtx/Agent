"""Private original task-result lineage for the existing native Teacher part."""

from typing import Literal, Self
from pydantic import model_validator
from .construction import ConstructionAttemptResult
from .evidence import EvidenceRef
from .lifecycle import OperationContext
from .state_scope import private_state_ref
from .teacher_attempt import TeacherFeedbackPolicy, PublishedTeacherAttempt
from .teacher_scope import TeacherContextScope
from .validation import Contract


class TaskTeacherInput(Contract):
    schema_version: Literal["task-teacher-input/1"] = "task-teacher-input/1"
    result: ConstructionAttemptResult
    scope: TeacherContextScope
    feedback: TeacherFeedbackPolicy
    operation: OperationContext

    @model_validator(mode="after")
    def original_source(self) -> Self:
        binding, op = self.result.intent.binding, self.operation
        if (self.scope.owner, self.scope.task) != (binding.run.owner, binding.task):
            raise ValueError("Teacher material must retain original task/run owner")
        if (op.run_id, op.owner_id, op.mode) != (
            self.scope.owner.run_id,
            self.scope.owner.owner_id,
            "execute",
        ) or any(
            v is not None for v in (op.attempt_id, op.allocation_id, op.recovery_ref)
        ):
            raise ValueError("Teacher material requires its original run-level command")
        if len(self.model_dump_json().encode()) > 256 * 1024:
            raise ValueError("Bounded private original task-result lineage required")
        return self


class TaskTeacherReceipt(Contract):
    schema_version: Literal["task-teacher-receipt/1"] = "task-teacher-receipt/1"
    original: TaskTeacherInput
    part: PublishedTeacherAttempt


class PublishedTaskTeacherAttempt(Contract):
    receipt_ref: EvidenceRef
    part: PublishedTeacherAttempt

    @model_validator(mode="after")
    def private_lineage(self) -> Self:
        private_state_ref(self.receipt_ref, "task-teacher-receipt/1")
        if self.receipt_ref.media_type != "application/json" or not (
            0 < self.receipt_ref.size_bytes <= 512 * 1024
        ):
            raise ValueError("Bounded private task/Teacher provenance required")
        return self
