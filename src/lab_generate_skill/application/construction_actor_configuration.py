"""Construction-only selected Actor check before inference and closed review."""

from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.construction import ConstructionPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.construction_actor_capabilities import (
    construction_actor_capabilities,
    check_construction_actor_request,
)
from .teacher_actor_reads import canonical


def verify_construction_actor_configuration(
    plan: ConstructionPlan,
    request: ActorRunRequest,
    evidence: EvidenceReader,
    control: OperationControl,
) -> None:
    check_construction_actor_request(plan, request)
    ref = request.context_configuration_ref
    if ref is None:
        return
    configuration = canonical(
        ref,
        "actor-context-configuration/1",
        ActorContextConfiguration,
        evidence,
        control,
        16 * 1024**2,
    )
    if plan.actor_context_configuration_ref is None:
        if isinstance(
            configuration.policy.actor_projection, AdaptiveObservationProjection
        ):
            raise OwnershipConflict(
                "New adaptive construction execution requires an explicit selected configuration declared to Generator"
            )
        return
    construction_actor_capabilities(plan, configuration)
