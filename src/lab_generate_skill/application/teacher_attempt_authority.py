"""Connect reviewed native parts to the existing complete construction source.

The original source admission is still mandatory. This decorator independently
binds every allowed part to its original Actor/Evaluation and candidate; it grants
no new task, source, model or feedback permission.
"""

from lab_generate_skill.domain.teacher_attempt import PublishedTeacherAttempt
from lab_generate_skill.domain.teacher_source import TeacherSourceBindings
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.teacher_source import TeacherSourceAuthority
from lab_generate_skill.ports.lifecycle import OperationControl
from .teacher_attempt_review import TeacherAttemptReviewDeps, review_teacher_attempt


class NativeTeacherSourceAuthority:
    def __init__(
        self,
        original: TeacherSourceAuthority,
        parts: tuple[PublishedTeacherAttempt, ...],
        deps: TeacherAttemptReviewDeps,
        recorded_operation: OperationContext,
    ) -> None:
        if original is None or deps.authority is None:
            raise ValueError(
                "Original source and native leaf authorities are mandatory"
            )
        checked = tuple(PublishedTeacherAttempt.model_validate(p) for p in parts)
        if not 4 <= len(checked) <= 6 or len(
            {p.source.attempt_id for p in checked}
        ) != len(checked):
            raise ValueError("All distinct ordered native source parts required")
        self.original, self.parts, self.deps, self.recorded_operation = (
            original,
            checked,
            deps,
            OperationContext.model_validate(recorded_operation),
        )

    def _verify(
        self,
        progress: ConstructionProgress,
        bindings: TeacherSourceBindings,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        bindings = TeacherSourceBindings.model_validate(bindings)
        if bindings.schema_version != "teacher-source-bindings/1":
            raise EvidenceIntegrityError(
                "Native-only source authority cannot ignore task-backed bindings v2"
            )
        results = progress.project().attempts
        if tuple(p.source for p in self.parts) != bindings.attempts or len(
            results
        ) != len(self.parts):
            raise EvidenceIntegrityError(
                "Native source registry lost/reordered original attempts"
            )
        for part, result in zip(self.parts, results, strict=True):
            receipt = review_teacher_attempt(
                part, self.deps, operation, control=control
            )
            if (
                receipt.original.scope.owner,
                receipt.original.scope.task,
                receipt.original.candidate_slot,
                receipt.original.evaluation_ref,
                receipt.source.attempt_id,
            ) != (
                progress.plan.run.owner,
                progress.plan.task.identity,
                result.intent.candidate_slot,
                result.evaluation_ref,
                result.intent.binding.attempt_id,
            ):
                raise EvidenceIntegrityError(
                    "Native source part is not the original construction attempt/evaluation"
                )

    def verify_prepare(
        self,
        progress: ConstructionProgress,
        bindings: TeacherSourceBindings,
        *,
        control: OperationControl,
    ) -> None:
        self.original.verify_prepare(progress, bindings, control=control)
        self._verify(progress, bindings, bindings.operation, control)

    def verify_recorded(
        self,
        progress: ConstructionProgress,
        bindings: TeacherSourceBindings,
        *,
        control: OperationControl,
    ) -> None:
        self.original.verify_recorded(progress, bindings, control=control)
        self._verify(progress, bindings, self.recorded_operation, control)
