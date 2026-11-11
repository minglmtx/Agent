"""Original source/model/fee admission and existing wire parameter validation."""

from typing import Protocol
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.teacher_assembly import TeacherRevisionAssemblyInput
from lab_generate_skill.domain.teacher_revision import TeacherRevisionPlan
from .lifecycle import OperationControl


class TeacherAssemblyAuthority(Protocol):
    def verify_build(
        self,
        progress: ConstructionProgress,
        original: TeacherRevisionAssemblyInput,
        *,
        control: OperationControl,
    ) -> None:
        """Verify actual original writer/run/claim, native source/feedback policy,
        model/parameters/provider and original configured fee/count/routing facts.
        No source/default allow. No model/resource call or new fee reservation.
        """
        ...

    def verify_recorded(
        self,
        progress: ConstructionProgress,
        original: TeacherRevisionAssemblyInput,
        plan: TeacherRevisionPlan,
        *,
        control: OperationControl,
    ) -> None:
        """Read original facts after progress/closure; grants no new dispatch."""
        ...


class TeacherWireParameterVerifier(Protocol):
    def __call__(self, raw: bytes, plan: TeacherRevisionPlan) -> None: ...
