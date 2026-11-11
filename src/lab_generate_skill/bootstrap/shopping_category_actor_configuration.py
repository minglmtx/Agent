"""Known category Actor inputs on existing profile/policy contracts; no loading."""

from dataclasses import dataclass
import unicodedata
from lab_generate_skill.adapters.models.context_tokens import actor_budget_profile
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
)
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_projection import (
    AdaptiveObservationProjection,
    ObservationTaskBinding,
)
from lab_generate_skill.domain.observation_read_policy import ObservationReadPolicy
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.optional_policies import InactivePolicy
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from .actor_context_policy import accepted_actor_context_policy


def category_actor_metadata(schema: str, *, public: bool = False) -> EvidenceMetadata:
    return EvidenceMetadata(
        media_type="application/json",
        content_schema=schema,
        visibility="public" if public else "private",
        producer="shopping-category-production-inputs-v1",
    )


@dataclass(frozen=True)
class CategoryNavigationActorInputs:
    context: ActorContextConfiguration
    context_ref: EvidenceRef
    policy: EngineeringActorPolicy
    parameters_ref: EvidenceRef
    skill_ref: EvidenceRef
    binding: ActorModelBinding
    software: bytes


def category_observation_projection() -> AdaptiveObservationProjection:
    """Explicit selected family configuration, separate from current permission.

    The values are frozen with this consumer and qualified by its own software
    and installed entry. Other sites/families do not inherit this declaration.
    """
    return AdaptiveObservationProjection(
        read_policy=ObservationReadPolicy(
            policy_id="shopping-category-adaptive-observation-v1",
            unicode_version=unicodedata.unidata_version,
            switch_tokens=24576,
            body_target_tokens=6000,
            body_max_tokens=8000,
            reads_per_observation=6,
            warn_remaining=2,
            consecutive_no_progress=2,
            max_ranges=4,
            directory_entries=32,
            search_hits=16,
            page_units=20,
            max_source_lines=100000,
        ),
        local_bindings=(
            ObservationTaskBinding(
                site="shopping",
                family="page_navigation",
                contract_version=1,
                split="train",
            ),
        ),
    )


def declare_category_actor_inputs(
    artifact: ReleaseArtifact,
    engine: ActorEngineConfig,
    binding: ActorModelBinding,
    routing_ref: EvidenceRef,
    parameters: LocalActorParameters,
    software_ref: EvidenceRef,
    software: bytes,
) -> CategoryNavigationActorInputs:
    artifact = ReleaseArtifact.model_validate(artifact)
    engine = ActorEngineConfig.model_validate(engine)
    binding = ActorModelBinding.model_validate(binding)
    parameters = LocalActorParameters.model_validate(parameters)
    if (
        engine.context_window,
        parameters.max_input_tokens,
        parameters.max_new_tokens,
    ) != (65536, 61440, 4096):
        raise ValueError(
            "Current category Actor64K/O4096 without output downshift required"
        )
    parameters_ref = evidence_reference(
        parameters.model_dump_json().encode(),
        category_actor_metadata("model-parameters/1"),
    )
    profile = actor_budget_profile(
        artifact,
        engine,
        binding,
        routing_ref,
        parameters,
        parameters_ref,
        soft_target=24576,
    )
    choice = category_observation_projection()
    context = ActorContextConfiguration(
        policy=accepted_actor_context_policy(software_ref, software, choice),
        profiles=(profile,) * 20,
    )
    context_ref = evidence_reference(
        context.model_dump_json().encode(),
        category_actor_metadata(context.schema_version),
    )
    skill = CompactSkill(
        title="Navigate",
        principle="1. Inspect the current target and open it.",
        when_to_apply="When navigating to the requested local page.",
    )
    skill_ref = evidence_reference(
        skill.model_dump_json().encode(),
        category_actor_metadata(skill.schema_version, public=True),
    )
    policy = EngineeringActorPolicy(
        skill=skill,
        memory=InactivePolicy(
            status="not_applicable",
            reason="Original engineering full action history; no cross-page memory enabled",
        ),
        max_generations=20,
        max_interactions=16,
        actor_projection=choice,
        actor_context_ref=context_ref,
        candidate_id="engineering-navigation-" + skill.content_digest,
        revision_round=0,
    )
    return CategoryNavigationActorInputs(
        context, context_ref, policy, parameters_ref, skill_ref, binding, software
    )


def publish_category_actor_inputs(
    actor: ActorResourceSpec,
    binding: ActorModelBinding,
    parameters: LocalActorParameters,
    software_ref: EvidenceRef,
    software: bytes,
    evidence: EvidenceStore,
    operation: OperationContext,
    control: OperationControl,
) -> CategoryNavigationActorInputs:
    actor = ActorResourceSpec.model_validate(actor)
    binding = ActorModelBinding.model_validate(binding)
    parameters = LocalActorParameters.model_validate(parameters)
    operation = OperationContext.model_validate(operation)
    if binding.release_ref != actor.release_ref or (
        operation.run_id,
        operation.owner_id,
        operation.mode,
    ) != (actor.token.owner.run_id, actor.token.owner.owner_id, "execute"):
        raise OwnershipConflict(
            "Category Actor inputs changed release or original owner"
        )
    frozen = declare_category_actor_inputs(
        actor.artifact,
        actor.engine_config,
        binding,
        actor.model_binding_ref,
        parameters,
        software_ref,
        software,
    )
    proposed = (
        (
            parameters.model_dump_json().encode(),
            category_actor_metadata("model-parameters/1"),
            frozen.parameters_ref,
        ),
        (
            frozen.context.model_dump_json().encode(),
            category_actor_metadata(frozen.context.schema_version),
            frozen.context_ref,
        ),
        (
            frozen.policy.skill.model_dump_json().encode(),
            category_actor_metadata(frozen.policy.skill.schema_version, public=True),
            frozen.skill_ref,
        ),
    )
    known: list[EvidenceRef] = []
    try:
        for raw, metadata, expected in proposed:
            control.checkpoint()
            reference = evidence.put(raw, metadata, control=control)
            known.append(reference)
            if reference != expected:
                raise OwnershipConflict(
                    "Category Actor input publication changed canonical bytes"
                )
        control.checkpoint()
    except BaseException as error:
        setattr(error, "category_actor_input_known_references", tuple(known))
        setattr(
            error,
            "category_actor_input_candidates",
            tuple(ref for _, _, ref in proposed),
        )
        raise
    return frozen
