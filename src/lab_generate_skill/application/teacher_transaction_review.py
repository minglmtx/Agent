"""Use the caller-held construction snapshot while its original lock is held.

The original Teacher verifier still checks every source/count/native response
fact. A scoped read view replaces only reentrant reads of that same journal.
No journal writes, lock relaxation, permission or model/fee path is introduced.
"""

from collections.abc import Callable
from dataclasses import dataclass
from lab_generate_skill.domain.construction import (
    ConstructionPlan,
    ProgressEvent,
    CallCompleted,
)
from lab_generate_skill.domain.construction_inputs import RevisionResult
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.teacher_revision import TeacherCompletion
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.teacher_revision import TeacherConstructionVerifier
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls


@dataclass(frozen=True)
class _TransactionConstructionRead:
    progress: ConstructionProgress
    operation: OperationContext
    controls: OperationControls
    enclosing: OperationControl

    def read(self, op: OperationContext) -> ConstructionProgress:
        if OperationContext.model_validate(op) != self.operation:
            raise OwnershipConflict(
                "Transaction snapshot requires its exact bounded read operation"
            )
        self.enclosing.checkpoint()
        control = self.controls.bind(op)
        control.checkpoint()
        result = ConstructionProgress.model_validate(self.progress)
        control.checkpoint()
        self.enclosing.checkpoint()
        return result

    def create(
        self, plan: ConstructionPlan, op: OperationContext
    ) -> ConstructionProgress:
        raise OwnershipConflict("Transaction construction snapshot is read-only")

    def append(
        self, event: ProgressEvent, expected_revision: int, op: OperationContext
    ) -> ConstructionProgress:
        raise OwnershipConflict("Transaction construction snapshot is read-only")


def construction_snapshot_read(
    progress: ConstructionProgress,
    operation: OperationContext,
    controls: OperationControls,
    enclosing: OperationControl,
) -> ConstructionJournal:
    """Reuse the exact original immutable read view outside the writer lock.

    The consumer must bind this data to its canonical sealed evidence. This is
    not a source/runtime permission and cannot append or create history.
    """
    progress = ConstructionProgress.model_validate(progress)
    operation = OperationContext.model_validate(operation)
    owner = progress.plan.run.owner
    if (
        operation.run_id,
        operation.owner_id,
        operation.attempt_id,
        operation.allocation_id,
        operation.recovery_ref,
    ) != (owner.run_id, owner.owner_id, None, None, None):
        raise OwnershipConflict(
            "Immutable construction read requires original run owner"
        )
    return _TransactionConstructionRead(progress, operation, controls, enclosing)


class TransactionTeacherReview:
    def __init__(
        self,
        bind: Callable[[ConstructionJournal], TeacherConstructionVerifier],
        read_operation: OperationContext,
        controls: OperationControls,
    ) -> None:
        if bind is None or controls is None:
            raise ValueError(
                "Original Teacher proof binder and operation controls required"
            )
        self.bind, self.operation, self.controls = (
            bind,
            OperationContext.model_validate(read_operation),
            controls,
        )

    def verify_construction(
        self,
        progress: ConstructionProgress,
        event: CallCompleted,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> TeacherCompletion:
        progress = ConstructionProgress.model_validate(progress)
        event = CallCompleted.model_validate(event)
        op = OperationContext.model_validate(operation)
        result = event.response
        if (
            not isinstance(result, RevisionResult)
            or result.schema_version != "revision-result/2"
        ):
            raise OwnershipConflict(
                "Transaction review requires original Teacher v2 result"
            )
        owner = progress.plan.run.owner
        for current in (op, self.operation):
            if (
                current.run_id,
                current.owner_id,
                current.attempt_id,
                current.allocation_id,
                current.recovery_ref,
            ) != (owner.run_id, owner.owner_id, None, None, None):
                raise OwnershipConflict(
                    "Transaction Teacher review requires original run-level scope"
                )
        control.checkpoint()
        self.controls.bind(self.operation).checkpoint()
        snapshot = _TransactionConstructionRead(
            progress, self.operation, self.controls, control
        )
        verifier = self.bind(snapshot)
        if verifier is None:
            raise ValueError("Original Teacher construction proof is mandatory")
        completion = verifier.verify_construction(progress, event, op, control=control)
        control.checkpoint()
        return TeacherCompletion.model_validate(completion)
