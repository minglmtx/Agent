"""Source permission and pure native message rendering; no default authority."""

from typing import Protocol
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.evaluation import Evaluation
from lab_generate_skill.domain.teacher_attempt import TeacherAttemptInput
from lab_generate_skill.domain.trace import InteractionTrace
from .lifecycle import OperationControl


class TeacherAttemptAuthority(Protocol):
    def verify_allowed(
        self,
        original: TeacherAttemptInput,
        request: ActorRunRequest,
        trace: InteractionTrace,
        evaluation: Evaluation,
        *,
        control: OperationControl,
    ) -> None:
        """Read-only original source/claim, actual exchanges and feedback permission.

        Verify original run/claim/history/Actor send and browser returns under the
        original resource authority, plus feedback authorization bytes and policy.
        Matching schemas/hashes or import/profile hints alone are insufficient.
        This does not approve new Actor or Teacher requests. No default allow.
        """
        ...


from lab_generate_skill.domain.teacher_actor_material import TeacherActorMaterial
from lab_generate_skill.domain.teacher_source import TeacherAttemptView


class TeacherAttemptComposer(Protocol):
    def __call__(self, material: TeacherActorMaterial) -> TeacherAttemptView: ...


class TeacherAttemptVerifier(Protocol):
    def __call__(
        self, material: TeacherActorMaterial, actual: TeacherAttemptView
    ) -> None:
        """Compare all actual fields without invoking the forward composer."""
        ...
