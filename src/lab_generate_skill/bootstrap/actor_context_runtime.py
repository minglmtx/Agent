"""Assemble context ports over an already acquired original model/resource."""

from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader, EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.observations import Observations
from lab_generate_skill.ports.trace_journal import TraceJournal
from lab_generate_skill.ports.actor import ActorRunAuthority
from lab_generate_skill.application.actor_context_inputs import (
    actor_context_configuration,
)
from lab_generate_skill.application.actor_context_preparation import (
    ControlledActorContext,
)
from lab_generate_skill.application.actor_context_review import (
    RecordedActorContextInputs,
)
from lab_generate_skill.adapters.models.actor_worker_client import SupervisedActorEngine
from lab_generate_skill.adapters.models.actor_context_records import (
    actor_context_document,
)
from lab_generate_skill.adapters.models.context_tokens import (
    actor_budget_profile,
    ActorContextTokenCounter,
)
from lab_generate_skill.adapters.models.context_count_review import (
    ActorContextCountReviewer,
)
from lab_generate_skill.adapters.models.actor_context_counters import (
    ActorContextCounters,
    ActorContextCountReviews,
)
from .context_projection import build_actor_context
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.adapters.plans.actor_observation_sources import (
    ActorObservationSources as ScopedActorObservationSources,
)


def freeze_actor_context(
    spec: ActorResourceSpec,
    parameters_refs: tuple[EvidenceRef, ...],
    policy: ContextProjectionPolicy,
    evidence: EvidenceReader,
    *,
    soft_target: int,
    control: OperationControl,
) -> ActorContextConfiguration:
    spec = ActorResourceSpec.model_validate(spec)
    binding = actor_context_document(
        evidence,
        spec.model_binding_ref,
        "model-binding/1",
        ActorModelBinding,
        16384,
        control,
    )
    if binding.release_ref != spec.release_ref:
        raise OwnershipConflict("Actor context binding changed original release")
    profiles = []
    for reference in parameters_refs:
        parameters = actor_context_document(
            evidence,
            reference,
            "model-parameters/1",
            LocalActorParameters,
            16384,
            control,
        )
        profiles.append(
            actor_budget_profile(
                spec.artifact,
                spec.engine_config,
                binding,
                spec.model_binding_ref,
                parameters,
                reference,
                soft_target=soft_target,
            )
        )
    return ActorContextConfiguration(policy=policy, profiles=tuple(profiles))


def live_actor_context(
    request: ActorRunRequest,
    spec: ActorResourceSpec,
    engine: SupervisedActorEngine,
    journal: TraceJournal,
    evidence: EvidenceStore,
    observations: Observations,
    authority: ActorRunAuthority,
    controls: OperationControls,
    *,
    control: OperationControl,
) -> tuple[ControlledActorContext, RecordedActorContextInputs]:
    spec = ActorResourceSpec.model_validate(spec)
    request = ActorRunRequest.model_validate(request)
    config = actor_context_configuration(request, evidence, control)
    guard, installed = engine.owner_guard, engine.installed_sources
    if (
        guard is None
        or installed is None
        or engine.session_id != spec.token.expected_resource_id
        or engine.artifact != spec.artifact
        or engine.config != spec.engine_config
        or request.model_allocation != spec.token
    ):
        raise OwnershipConflict(
            "Context assembly requires original acquired Actor engine/spec"
        )
    if guard.controller != spec.slurm.allocation.facts.writer or (
        installed.manifest_sha256,
        installed.executable,
    ) != (spec.release_ref.sha256, spec.python_executable):
        raise OwnershipConflict(
            "Context assembly changed original installation/controller"
        )
    counters = {}
    reviewers = {}
    for profile in config.profiles:
        if profile.routing_ref != spec.model_binding_ref:
            raise OwnershipConflict("Actor context changed original model route")
        if profile.digest in counters:
            continue
        binding = actor_context_document(
            evidence,
            profile.routing_ref,
            "model-binding/1",
            ActorModelBinding,
            16384,
            control,
        )
        if binding.release_ref != spec.release_ref:
            raise OwnershipConflict("Actor profile changed original release")
        parameters = actor_context_document(
            evidence,
            profile.configuration_ref,
            "model-parameters/1",
            LocalActorParameters,
            16384,
            control,
        )
        counters[profile.digest] = ActorContextTokenCounter(
            engine, evidence, profile, binding, parameters, session_id=engine.session_id
        )
        reviewers[profile.digest] = ActorContextCountReviewer(
            evidence,
            profile,
            binding,
            parameters,
            spec.artifact,
            spec.engine_config,
            session_id=engine.session_id,
            guard=guard,
            installed_sources=installed,
        )
    counter_registry = ActorContextCounters(counters)
    count_review_registry = ActorContextCountReviews(reviewers)
    source_factory = None
    if isinstance(config.policy.actor_projection, AdaptiveObservationProjection):
        from lab_generate_skill.application.actor_rejection_progress import (
            RecordedActorRejectionProgress,
        )

        source_factory = ScopedActorObservationSources(
            request,
            journal,
            evidence,
            authority,
            controls,
            config,
            counter_registry,
            count_review_registry,
            rejections=RecordedActorRejectionProgress(evidence),
        )
    project, protection = build_actor_context(
        config.policy,
        indices=None if source_factory is None else source_factory.index_for_public,
    )
    input_review = RecordedActorContextInputs(
        evidence,
        observations,
        project,
        protection,
        count_review_registry,
        retain_inputs=True,
        request=request,
        observation_sources=source_factory,
    )
    return (
        ControlledActorContext(
            request,
            journal,
            evidence,
            observations,
            authority,
            controls,
            project,
            protection,
            counter_registry,
            inputs=input_review,
            observation_sources=source_factory,
        ),
        input_review,
    )
