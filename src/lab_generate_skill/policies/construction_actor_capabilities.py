"""One pure selected-configuration projection for prepare, send and review."""

from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_projection import (
    AdaptiveObservationProjection,
    FullAxProjection,
    check_projection_task,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.construction import ConstructionPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.generator_actor_capabilities import (
    GeneratorActorCapabilities,
    GeneratorActorReadLimits,
)


def construction_actor_capabilities(
    plan: ConstructionPlan, configuration: ActorContextConfiguration
) -> GeneratorActorCapabilities:
    actor = next(model for model in plan.models if model.role == "actor")
    if any(
        profile.routing_ref != actor.model_binding_ref or profile.model != actor.model
        for profile in configuration.profiles
    ):
        raise OwnershipConflict(
            "Selected Actor configuration differs from the construction model role"
        )
    projection = configuration.policy.actor_projection
    if projection is None:
        raise OwnershipConflict(
            "Selected construction Actor requires an explicit observation projection"
        )
    check_projection_task(projection, plan.task.identity)
    tools: tuple[str, ...] = ()
    limits = None
    if isinstance(projection, AdaptiveObservationProjection):
        if projection.supports_local(plan.task.identity):
            mode = "adaptive_compact_full_or_local"
            tools = ("list_regions", "read_region", "search_regions")
            policy = projection.read_policy
            limits = GeneratorActorReadLimits(
                body_target_tokens=policy.body_target_tokens,
                body_max_tokens=policy.body_max_tokens,
                reads_per_observation=policy.reads_per_observation,
                warn_remaining=policy.warn_remaining,
                consecutive_no_progress=policy.consecutive_no_progress,
                max_ranges=policy.max_ranges,
            )
        else:
            mode = "compact_full_ax"
    elif isinstance(projection, FullAxProjection):
        mode = "current_page_full_ax"
    else:
        mode = "current_task_structured_map"
    return GeneratorActorCapabilities.model_validate(
        dict(
            observation_mode=mode,
            conditional_read_tools=tools,
            read_limits=limits,
        )
    )


def check_construction_actor_request(
    plan: ConstructionPlan, request: ActorRunRequest
) -> None:
    if plan.actor_context_configuration_ref is not None and (
        request.schema_version != "actor-run-request/2"
        or request.context_configuration_ref != plan.actor_context_configuration_ref
        or request.task.identity != plan.task.identity
    ):
        raise OwnershipConflict(
            "Actual construction Actor changed the configuration declared to Generator"
        )
