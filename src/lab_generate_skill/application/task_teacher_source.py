"""Persisted complete task lineage at the original Teacher source boundary.

Original run/claim/source and native leaf authorities remain mandatory. Private
receipt refs are read from explicit bindings2, never inferred from CAS contents.
No composer, model, sender or recovery is invoked here.
"""

from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_teacher import (
    PublishedTaskTeacherAttempt,
    TaskTeacherReceipt,
)
from lab_generate_skill.domain.teacher_source import TeacherSourceBindings
from lab_generate_skill.domain.task_execution_result import (
    TaskAttemptResult,
    ExecutedTaskReceipt,
)
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.teacher_source import TeacherSourceAuthority
from .task_teacher_review import TaskTeacherReviewDeps, review_task_teacher_attempt
from .teacher_actor_reads import canonical


class CompletedTaskTeacherSourceAuthority:
    def __init__(
        self,
        original: TeacherSourceAuthority,
        deps: TaskTeacherReviewDeps,
        contexts: ContextRecords,
        recorded_operation: OperationContext,
    ) -> None:
        if (
            original is None
            or not callable(getattr(original, "verify_prepare", None))
            or not callable(getattr(original, "verify_recorded", None))
            or not isinstance(deps, TaskTeacherReviewDeps)
            or contexts is None
            or not callable(getattr(contexts, "load_equivalence", None))
        ):
            raise ValueError(
                "Original source and complete task/native review dependencies required"
            )
        self.original, self.deps, self.contexts = original, deps, contexts
        self.recorded_operation = OperationContext.model_validate(recorded_operation)

    def _verify(
        self,
        progress: ConstructionProgress,
        bindings: TeacherSourceBindings,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        progress = ConstructionProgress.model_validate(progress)
        bindings = TeacherSourceBindings.model_validate(bindings)
        results = progress.project().attempts
        refs = bindings.task_receipt_refs
        if (
            bindings.schema_version != "teacher-source-bindings/2"
            or refs is None
            or len(results) != len(refs)
        ):
            raise EvidenceIntegrityError(
                "Task source requires complete persisted bindings2 receipt history"
            )
        for reference, source, result in zip(
            refs, bindings.attempts, results, strict=True
        ):
            control.checkpoint()
            receipt = canonical(
                reference,
                "task-teacher-receipt/1",
                TaskTeacherReceipt,
                self.deps.original.evidence,
                control,
                512 * 1024,
            )
            if receipt.part.source != source or receipt.original.result != result:
                raise EvidenceIntegrityError(
                    "Task receipt is not the original complete source/result"
                )
            if receipt.original.operation != bindings.operation:
                raise OwnershipConflict(
                    "Task parts and source require the same original material command"
                )
            published = PublishedTaskTeacherAttempt(
                receipt_ref=reference, part=receipt.part
            )
            reviewed = review_task_teacher_attempt(
                published, self.deps, operation, control=control
            )
            if reviewed != receipt:
                raise EvidenceIntegrityError(
                    "Original task source changed during independent review"
                )
            envelope = canonical(
                result.attempt_ref,
                "attempt-result/1",
                TaskAttemptResult,
                self.deps.original.evidence,
                control,
            )
            executed = canonical(
                envelope.execution_ref,
                "executed-task-receipt/1",
                ExecutedTaskReceipt,
                self.deps.original.evidence,
                control,
            )
            equivalent = self.contexts.load_equivalence(
                executed.equivalence_ref, operation
            )
            scope = receipt.original.scope
            if (
                equivalent.status != "equivalent"
                or equivalent.source_context_receipt_ref
                != progress.plan.context_receipt_ref
                or equivalent.candidate_baseline_ref != executed.baseline_ref
                or (
                    equivalent.scope.owner,
                    equivalent.scope.task,
                    equivalent.scope.context_id,
                    equivalent.scope.attempt_id,
                )
                != (
                    scope.owner,
                    scope.task,
                    scope.context_id,
                    result.intent.binding.attempt_id,
                )
            ):
                raise EvidenceIntegrityError(
                    "Task source lost measured candidate-to-original context equivalence"
                )
        control.checkpoint()

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
