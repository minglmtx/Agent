"""Explicit role strategy assembly; not source admission or model dispatch."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab_generate_skill.teacher.context_projection import TeacherContextProjector
    from lab_generate_skill.teacher.context_protection import TeacherContextProtection

from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.actor.context_projection import ActorContextProjector
from lab_generate_skill.actor.context_protection import ActorContextProtection
from lab_generate_skill.actor.context_source import checked_actor_policy
from .actor_projection import build_actor_projection
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.actor.adaptive_projection import AdaptiveActorProjector
from lab_generate_skill.actor.adaptive_protection import (
    AdaptiveActorProtection,
    IndexProvider,
)
from lab_generate_skill.ports.context_projection import (
    ContextInputProjector,
    ContextProtectionVerifier,
)


def build_actor_context(
    policy: ContextProjectionPolicy,
    *,
    indices: IndexProvider | None = None,
) -> tuple[ContextInputProjector, ContextProtectionVerifier]:
    policy = checked_actor_policy(policy)
    if isinstance(policy.actor_projection, AdaptiveObservationProjection):
        return AdaptiveActorProjector(policy, indices), AdaptiveActorProtection(
            policy, indices
        )
    structural = None
    if "structural_ax" in policy.candidate_order:
        assert policy.actor_projection is not None
        structural = build_actor_projection(policy.actor_projection)
    return ActorContextProjector(policy, structural), ActorContextProtection(policy)


def build_teacher_context(
    policy: ContextProjectionPolicy,
) -> tuple["TeacherContextProjector", "TeacherContextProtection"]:
    """Assemble the typed permitted role; neither credentials nor send permission."""
    from lab_generate_skill.teacher.context_source import checked_teacher_policy
    from lab_generate_skill.teacher.context_projection import TeacherContextProjector
    from lab_generate_skill.teacher.context_protection import TeacherContextProtection

    policy = checked_teacher_policy(policy)
    return TeacherContextProjector(policy), TeacherContextProtection(policy)
