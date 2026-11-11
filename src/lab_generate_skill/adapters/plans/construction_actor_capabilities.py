"""Read the explicitly selected private configuration; expose public facts only."""

from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.construction import ConstructionPlan
from lab_generate_skill.domain.generator_actor_capabilities import (
    GeneratorActorCapabilities,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.construction_actor_capabilities import (
    construction_actor_capabilities,
)
from .state_reads import StateReads


def selected_actor_capabilities(
    plan: ConstructionPlan, reads: StateReads, control: OperationControl
) -> GeneratorActorCapabilities | None:
    ref = plan.actor_context_configuration_ref
    if ref is None:
        return None
    configuration = reads.parse(
        ref, "actor-context-configuration/1", ActorContextConfiguration, control
    )
    return construction_actor_capabilities(plan, configuration)
