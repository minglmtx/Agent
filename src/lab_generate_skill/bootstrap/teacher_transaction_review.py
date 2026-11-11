"""Original Teacher proof bound to the original transaction's immutable view.

The trusted binder must use the supplied ConstructionJournal for source review;
all other original claim/context/native/provider/count proof dependencies remain.
"""

from collections.abc import Callable
from lab_generate_skill.application.teacher_transaction_review import (
    TransactionTeacherReview,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.teacher_revision import TeacherConstructionVerifier
from lab_generate_skill.ports.lifecycle import OperationControls


def transaction_teacher_review(
    bind: Callable[[ConstructionJournal], TeacherConstructionVerifier],
    read_operation: OperationContext,
    *,
    controls: OperationControls,
) -> TransactionTeacherReview:
    return TransactionTeacherReview(bind, read_operation, controls)
