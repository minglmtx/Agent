"""Real public Actor candidates; reuse baseline/Q projection, never count or save."""

from lab_generate_skill.domain.context_preparation import ContextInputDraft
from lab_generate_skill.domain.context_projection import (
    AllowedContextSource,
    ContextProjectionPolicy,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.actor import ActorProjection
from .context_source import actor_source, checked_actor_policy
from .context_protection import actor_audit
from .prompting import prepare_actor


class ActorContextProjector:
    def __init__(
        self, policy: ContextProjectionPolicy, structural: ActorProjection | None
    ) -> None:
        self._policy = checked_actor_policy(policy)
        if ("structural_ax" in policy.candidate_order) != (structural is not None):
            raise ValueError(
                "Explicit original structural projector required only when selected"
            )
        self._structural = structural

    def project(
        self,
        source: AllowedContextSource,
        original: bytes,
        policy: ContextProjectionPolicy,
    ) -> tuple[ContextInputDraft, ...]:
        if checked_actor_policy(policy) != self._policy:
            raise OwnershipConflict("Actor projector changed frozen policy")
        turn = actor_source(source, original, policy)
        drafts = []
        for kind in policy.candidate_order:
            if kind == "identity":
                prompt = prepare_actor(turn)
            else:
                assert self._structural is not None
                prompt = self._structural(turn)
            drafts.append(
                ContextInputDraft(
                    candidate_id=kind,
                    kind=kind,
                    source=source,
                    policy_sha256=policy.digest,
                    input_bytes=prompt.model_dump_json().encode(),
                    audit=actor_audit(source, turn, policy, kind, prompt),
                )
            )
        return tuple(drafts)
