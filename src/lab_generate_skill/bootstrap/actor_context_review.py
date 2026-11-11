"""Assemble only read capabilities from original acquired facts after closure."""

import json
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.adapters.plans.recorded_observation_sources import (
    RecordedActorObservationSources,
)
from lab_generate_skill.application.actor_rejection_progress import (
    RecordedActorRejectionProgress,
)
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.actor_step import ActorStepStarted
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.observations import Observations
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.application.actor_context_inputs import (
    actor_context_configuration,
)
from lab_generate_skill.application.actor_context_review import (
    RecordedActorContextInputs,
)
from lab_generate_skill.adapters.models.actor_context_records import (
    actor_context_document,
    actor_context_bytes,
)
from lab_generate_skill.adapters.models.context_count_review import (
    ActorContextCountReviewer,
)
from lab_generate_skill.adapters.models.actor_context_counters import (
    ActorContextCountReviews,
)
from lab_generate_skill.adapters.models.actor_step import same_allocation
from lab_generate_skill.adapters.models.actor_resource_records import check_operation
from lab_generate_skill.adapters.slurm.step_launch import actor_step_name
from lab_generate_skill.adapters.processes.wire_json import json_object
from .context_projection import build_actor_context


def closed_actor_context(
    request: ActorRunRequest,
    executions: tuple[LocalActorExecution, ...],
    evidence: EvidenceReader,
    observations: Observations,
    *,
    control: OperationControl,
) -> RecordedActorContextInputs:
    request = ActorRunRequest.model_validate(request)
    config = actor_context_configuration(request, evidence, control)
    if not executions:
        raise EvidenceIntegrityError(
            "Closed Actor context requires original model executions"
        )
    executions = tuple(LocalActorExecution.model_validate(x) for x in executions)
    binding = executions[0].call.binding
    if binding.resource != request.model_allocation or any(
        x.call.binding != binding or x.call.intent.scope != request.scope
        for x in executions
    ):
        raise OwnershipConflict(
            "Context review changed original Actor resource/attempt"
        )
    spec = actor_context_document(
        evidence,
        binding.spec_ref,
        "actor-resource-spec/1",
        ActorResourceSpec,
        8 * 1024**2,
        control,
    )
    if (spec.token, spec.release_ref, spec.model_binding_ref) != (
        binding.resource,
        binding.release_ref,
        binding.model_binding_ref,
    ):
        raise OwnershipConflict("Context review spec differs from original binding")
    acquired = json_object(
        actor_context_bytes(
            evidence,
            binding.acquired_ref,
            "actor-resource-fact/1",
            16 * 1024**2,
            control,
        )
    )
    if (
        set(acquired)
        != {
            "schema_version",
            "kind",
            "token",
            "spec_sha256",
            "owner_guard",
            "worker",
            "installed_sources",
            "operation",
            "step",
        }
        or acquired["schema_version"] != "actor-resource-fact/1"
        or acquired["kind"] != "acquired"
        or acquired["token"] != spec.token.model_dump(mode="json")
        or acquired["spec_sha256"] != binding.spec_ref.sha256
    ):
        raise EvidenceIntegrityError("Context review lost exact original acquisition")
    guard = ProcessOwnerGuard.model_validate_json(json.dumps(acquired["owner_guard"]))
    installed = InstalledReleaseSources.model_validate_json(
        json.dumps(acquired["installed_sources"])
    )
    started = ActorStepStarted.model_validate_json(json.dumps(acquired["step"]))
    acquired_operation = OperationContext.model_validate_json(
        json.dumps(acquired["operation"])
    )
    check_operation(spec, acquired_operation, "execute")
    same_allocation(spec.slurm.allocation, started.allocation)
    if (
        acquired["worker"] != guard.worker.model_dump(mode="json")
        or guard.controller != spec.slurm.allocation.facts.writer
        or started.controller.target.worker.writer != guard.worker
        or started.controller.target.step_name != actor_step_name(spec.token)
        or (installed.manifest_sha256, installed.executable)
        != (spec.release_ref.sha256, spec.python_executable)
        or any(x.guard != guard for x in executions)
    ):
        raise OwnershipConflict(
            "Context review guard/installation/worker differs from original acquired domain"
        )
    reviewers = {}
    for profile in config.profiles:
        if profile.routing_ref != spec.model_binding_ref:
            raise OwnershipConflict("Closed count profile changed original model route")
        if profile.digest in reviewers:
            continue
        model = actor_context_document(
            evidence,
            profile.routing_ref,
            "model-binding/1",
            ActorModelBinding,
            16384,
            control,
        )
        if model.release_ref != spec.release_ref:
            raise OwnershipConflict("Closed count profile changed original release")
        parameters = actor_context_document(
            evidence,
            profile.configuration_ref,
            "model-parameters/1",
            LocalActorParameters,
            16384,
            control,
        )
        reviewers[profile.digest] = ActorContextCountReviewer(
            evidence,
            profile,
            model,
            parameters,
            spec.artifact,
            spec.engine_config,
            session_id=spec.token.expected_resource_id,
            guard=guard,
            installed_sources=installed,
        )
    sources = (
        RecordedActorObservationSources(
            config, evidence, rejections=RecordedActorRejectionProgress(evidence)
        )
        if isinstance(config.policy.actor_projection, AdaptiveObservationProjection)
        else None
    )
    project, protection = build_actor_context(
        config.policy, indices=None if sources is None else sources.index_for_public
    )
    return RecordedActorContextInputs(
        evidence,
        observations,
        project,
        protection,
        ActorContextCountReviews(reviewers),
        observation_sources=sources,
    )
