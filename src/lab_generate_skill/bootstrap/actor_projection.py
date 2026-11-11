"""Fixed Actor projector assembly from a complete explicit frozen selection."""

from lab_generate_skill.domain.actor_projection import (
    ActorProjectionConfiguration,
    FullAxProjection,
    AdaptiveObservationProjection,
    actor_projection_configuration,
)
from lab_generate_skill.ports.actor import ActorProjection
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.actor.map_rails_projection import MapRailsActorProjection


def build_actor_projection(
    configuration: ActorProjectionConfiguration,
) -> ActorProjection:
    configuration = actor_projection_configuration(configuration)
    if isinstance(configuration, FullAxProjection):
        return prepare_actor
    if isinstance(configuration, AdaptiveObservationProjection):
        raise ValueError(
            "Adaptive Actor projection requires the actual source/window factory and controlled context"
        )
    return MapRailsActorProjection(configuration)
