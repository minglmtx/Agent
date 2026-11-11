"""Original source qualification and trace/feedback projection provenance.

No default allow. These hooks must verify actual original context/claim/history,
every original Actor request/trace, full allowed attempt projection and private
feedback exclusion. Labels, matching refs or import/profile hints do not prove it.
For explicit bindings2 the final composed authority also verifies every stored
private task receipt and its complete closure/Reset lineage. Native-only
authorities must reject2 rather than discard the new references.
"""

from typing import Protocol
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.teacher_source import TeacherSourceBindings
from .lifecycle import OperationControl


class TeacherSourceAuthority(Protocol):
    def verify_prepare(
        self,
        progress: ConstructionProgress,
        bindings: TeacherSourceBindings,
        *,
        control: OperationControl,
    ) -> None:
        """Admit original eligible history/request; pending/unknown cannot renew."""
        ...

    def verify_recorded(
        self,
        progress: ConstructionProgress,
        bindings: TeacherSourceBindings,
        *,
        control: OperationControl,
    ) -> None:
        """Verify original allowed projections after closure without new permission."""
        ...


from lab_generate_skill.domain.teacher_scope import TeacherContextScope
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.teacher_source import TeacherAttemptView
from lab_generate_skill.domain.teacher_input import AllowedTeacherEvidence


class TeacherSourceComposer(Protocol):
    def __call__(
        self,
        scope: TeacherContextScope,
        task: PublicTask,
        teacher_round: int,
        instructions: str,
        initial: str,
        skills: tuple[CompactSkill, ...],
        attempts: tuple[TeacherAttemptView, ...],
        best: int | None,
    ) -> AllowedTeacherEvidence:
        """Pure deterministic complete field composition, no source filtering."""
        ...
