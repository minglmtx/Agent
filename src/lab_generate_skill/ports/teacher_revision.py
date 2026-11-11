"""Original revision plan and response parsing; no alternative model/fee ledger."""

from typing import Protocol
from lab_generate_skill.domain.teacher_revision import (
    BoundTeacherRevisionPlan,
    TeacherCompletion,
)
from lab_generate_skill.domain.construction import CallCompleted
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl


class TeacherRevisionPlans(Protocol):
    def load(
        self, request_id: str, operation: OperationContext, *, control: OperationControl
    ) -> BoundTeacherRevisionPlan:
        """Read original immutable plan; missing/unknown identity cannot create one."""
        ...

    def load_recorded(
        self, request_id: str, operation: OperationContext, *, control: OperationControl
    ) -> BoundTeacherRevisionPlan:
        """Read facts for a same-run construction command; grants no send permission."""
        ...


class TeacherConstructionVerifier(Protocol):
    def verify_construction(
        self,
        progress: ConstructionProgress,
        event: CallCompleted,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> TeacherCompletion:
        """Verify exact registered Teacher v2 result before construction commit."""
        ...


class TeacherCompletionDecoder(Protocol):
    def decode(self, raw: bytes) -> TeacherCompletion:
        """Pure parse of original saved response, including known usage or unknown."""
        ...
