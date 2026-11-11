"""Strict canonical public Actor source; no claim, private evidence or I/O."""

from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.actor_projection import (
    check_projection_task,
    AdaptiveObservationProjection,
)
from lab_generate_skill.domain.context_projection import (
    ActorContextSource,
    AllowedContextSource,
    ContextProjectionPolicy,
)
from lab_generate_skill.domain.context_transformation import context_bytes_sha
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict

ACTOR_PROTECTION_RULES = (
    "original_public_scope",
    "task_skill_constraints",
    "complete_history_errors_tabs",
    "all_page_relations",
    "complete_transform_audit",
)
ADAPTIVE_ACTOR_PROTECTION_RULES = (
    "original_public_scope",
    "task_skill_constraints",
    "complete_history_errors_tabs",
    "represented_public_relations",
    "bounded_read_capability",
    "complete_transform_audit",
)


def checked_actor_policy(policy: ContextProjectionPolicy) -> ContextProjectionPolicy:
    policy = ContextProjectionPolicy.model_validate(policy)
    adaptive = isinstance(policy.actor_projection, AdaptiveObservationProjection)
    expected_rules = (
        ADAPTIVE_ACTOR_PROTECTION_RULES if adaptive else ACTOR_PROTECTION_RULES
    )
    if policy.role != "actor" or policy.protected_rules != expected_rules:
        raise ValueError("Original Actor protection contract required")
    if any(
        kind
        not in (
            ("compact_full_ax", "local_ax")
            if adaptive
            else ("identity", "structural_ax")
        )
        for kind in policy.candidate_order
    ):
        raise ValueError("Unsupported Actor format must not silently fall back")
    return policy


def actor_source(
    source: AllowedContextSource, raw: bytes, policy: ContextProjectionPolicy
) -> ActorPublicTurn:
    if not isinstance(source, ActorContextSource):
        raise TypeError("Actor projection cannot receive Teacher evidence")
    source = ActorContextSource.model_validate(source)
    policy = checked_actor_policy(policy)
    if type(raw) is not bytes or (len(raw), context_bytes_sha(raw)) != (
        source.turn_ref.size_bytes,
        source.turn_ref.sha256,
    ):
        raise EvidenceIntegrityError(
            "Actor turn differs from original complete public bytes"
        )
    turn = ActorPublicTurn.model_validate_json(raw)
    adaptive = isinstance(policy.actor_projection, AdaptiveObservationProjection)
    if (
        adaptive != (turn.schema_version == "actor-public-turn/2")
        or turn.schema_version != source.turn_ref.content_schema
    ):
        raise OwnershipConflict(
            "Actor source version differs from its actual selected strategy"
        )
    if adaptive:
        public = turn.observation_source
        assert public is not None and isinstance(
            policy.actor_projection, AdaptiveObservationProjection
        )
        if (
            public.snapshot.scope != source.scope
            or public.policy != policy.actor_projection.read_policy
            or public.read_result_ref != source.active_read_ref
        ):
            raise OwnershipConflict(
                "Actor source changed original read scope/policy/window lineage"
            )
        if (
            public.eligibility == "local_supported"
            and not policy.actor_projection.supports_local(turn.task.identity)
        ):
            raise OwnershipConflict(
                "Local source family/contract is not in the frozen capability scope"
            )
    if turn.model_dump_json().encode() != raw:
        raise EvidenceIntegrityError(
            "Actor public turn must retain canonical schema and bytes"
        )
    observed = turn.observation.record
    if (turn.task.identity, observed.context_id, observed.attempt_id) != (
        source.scope.task,
        source.scope.context_id,
        source.scope.attempt_id,
    ):
        raise OwnershipConflict(
            "Actor public turn changed original task/context/attempt"
        )
    if policy.actor_projection is not None:
        check_projection_task(policy.actor_projection, turn.task.identity)
    return turn
