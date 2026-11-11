"""New prompt revisions from accepted public fixtures; no production replay."""

from typing import Any

from lab_generate_skill.domain.actor_observation_source import ActorObservationSource
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.actor_proposal_feedback import (
    ActorInvalidProposalProgress,
)
from lab_generate_skill.domain.context_projection import (
    ActorContextSource,
    ContextProjectionPolicy,
)
from lab_generate_skill.domain.observation import (
    ObservationArtifact,
    ResolvedObservation,
)
from lab_generate_skill.domain.observation_read_policy import ObservationReadPolicy
from lab_generate_skill.domain.observation_viewport import VIEWPORT_NAME
from lab_generate_skill.policies.observation_index import (
    ObservationIndex,
    index_public_ax,
)

from test_adaptive_context_repair import pure_case
from test_public_viewport_handoff import index_for, window
from retrieval_fixtures import reference


def guidance_case(
    *,
    tools: tuple[str, ...] = ("list_regions", "read_region", "search_regions"),
    measured: str | None = None,
    geometry_unknown: bool = False,
    changes: dict[str, Any] | None = None,
    reads_used: int = 0,
) -> tuple[
    ActorPublicTurn, ObservationIndex, ActorContextSource, ContextProjectionPolicy
]:
    public, old_index, _, policy = pure_case(tools=tools)
    observed = public.observation.record
    viewport = None
    if measured is not None:
        old_index, observed, viewport = index_for(measured)
        if geometry_unknown:
            viewport = viewport.model_copy(
                update={
                    "elements": tuple(
                        element.model_copy(update={"visibility": None, "box": None})
                        for element in viewport.elements
                    )
                }
            )
            observed = observed.model_copy(
                update={
                    "artifacts": (
                        ObservationArtifact(
                            name=VIEWPORT_NAME, reference=viewport.reference
                        ),
                    )
                }
            )
    read_policy = ObservationReadPolicy.model_validate(
        {
            **old_index.policy.model_dump(),
            "schema_version": "observation-read-policy/2",
            "max_consecutive_invalid_proposals": 3,
            "max_identical_invalid_proposals": 2,
            "warn_remaining": 3,
            **(changes or {}),
        }
    )
    index = index_public_ax(
        reference(observed, "observation/1", "public"),
        observed.model_dump_json().encode(),
        ResolvedObservation(record=observed, text=observed.text),
        old_index.snapshot.scope,
        read_policy,
        viewport=viewport,
    )
    selected_window = window(index) if tools else None
    read_result_ref = (
        reference(selected_window, "observation-read-result/2", "public")
        if reads_used
        else None
    )
    source = ActorObservationSource.model_validate(
        dict(
            schema_version="actor-observation-source/2",
            invalid_proposals=ActorInvalidProposalProgress(),
            snapshot=index.snapshot,
            policy=read_policy,
            eligibility="local_supported" if tools else "full_required",
            reason="isolated_guidance_fixture",
            tools=tools,
            local_window=selected_window,
            window_origin=(
                ("actor_returned" if reads_used else "automatic_initial")
                if tools
                else "none"
            ),
            read_result_ref=read_result_ref,
            reads_used=reads_used,
            no_progress=0,
        )
    )
    public = ActorPublicTurn.model_validate(
        public.model_copy(
            update={
                "task": public.task.model_copy(
                    update={
                        "identity": observed.task,
                        "allowed_actions": (
                            "click",
                            "fill",
                            "scroll",
                            "tab_focus",
                            "send_msg_to_user",
                        ),
                    }
                ),
                "observation": ResolvedObservation(record=observed, text=observed.text),
                "observation_source": source,
            }
        )
    )
    selected = policy.actor_projection
    assert isinstance(selected, AdaptiveObservationProjection)
    policy = ContextProjectionPolicy.model_validate(
        policy.model_copy(
            update={
                "actor_projection": selected.model_copy(
                    update={"read_policy": read_policy}
                ),
            }
        )
    )
    allowed = ActorContextSource(
        scope=index.snapshot.scope,
        candidate_id="guidance-fixture",
        revision_round=0,
        turn_ref=reference(public, "actor-public-turn/2", "public"),
        active_read_ref=read_result_ref,
    )
    return public, index, allowed, policy
