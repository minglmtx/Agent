"""Exact existing execution-policy ref selects both Actor projection and review."""

import hashlib
from lab_generate_skill.domain.actor_projection import (
    ActorProjectionConfiguration,
    FullAxProjection,
    actor_projection_configuration,
    check_projection_task,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.application.actor_context_inputs import (
    actor_context_configuration,
)
from lab_generate_skill.bootstrap.actor_context_runtime import freeze_actor_context
from lab_generate_skill.adapters.models.actor_context_records import (
    actor_context_document,
)
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.trace_plan import TracePlan
from lab_generate_skill.domain.run_plan import RunPlan, ExecutionWorkload
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl


def read_source_projection(
    ref: EvidenceRef,
    request: ActorRunRequest,
    trace: TracePlan,
    store: EvidenceReader,
    control: OperationControl,
) -> ActorProjectionConfiguration:
    if (
        ref.media_type != "application/json"
        or ref.visibility != "private"
        or not 0 < ref.size_bytes <= 1024**2
        or ref.content_schema
        not in (
            "engineering-execution-policy/1",
            "engineering-execution-policy/2",
            "engineering-execution-policy/3",
        )
    ):
        raise EvidenceIntegrityError(
            "Exact engineering Actor execution policy required"
        )
    raw = store.read(ref, control=control)
    if len(raw) != ref.size_bytes or hashlib.sha256(raw).hexdigest() != ref.sha256:
        raise EvidenceIntegrityError("Actor execution policy changed original bytes")
    if ref.content_schema == "engineering-execution-policy/3":
        policy = EngineeringActorPolicy.model_validate_json(raw)
        if (
            policy.model_dump_json().encode() != raw
            or (
                policy.skill,
                policy.memory,
                policy.max_generations,
                policy.max_interactions,
                policy.actor_context_ref,
                policy.candidate_id,
                policy.revision_round,
            )
            != (
                request.skill,
                request.memory,
                trace.max_generations,
                trace.max_interactions,
                request.context_configuration_ref,
                request.candidate_id,
                request.revision_round,
            )
            or request.schema_version != "actor-run-request/2"
        ):
            raise EvidenceIntegrityError(
                "Actor policy lost original context/candidate/round binding"
            )
        config = actor_context_configuration(request, store, control)
        if (
            config.policy.actor_projection or FullAxProjection()
        ) != policy.actor_projection:
            raise EvidenceIntegrityError(
                "Actor context and execution page policy differ"
            )
        check_projection_task(policy.actor_projection, request.task.identity)
        return policy.actor_projection
    if request.schema_version != "actor-run-request/1":
        raise EvidenceIntegrityError(
            "Historical policy cannot authorize new Actor context"
        )
    try:
        value = json_object(raw)
    except (ValueError, TypeError, UnicodeDecodeError) as error:
        raise EvidenceIntegrityError(
            "Invalid complete Actor execution policy JSON"
        ) from error
    if not isinstance(value, dict):
        raise EvidenceIntegrityError("Actor execution policy must be a complete object")
    if (
        value.get("engineering_only") is not True
        or type(value.get("max_generations")) is not int
        or type(value.get("max_interactions")) is not int
    ):
        raise EvidenceIntegrityError(
            "Actor execution limits require exact original types"
        )
    expected = dict(
        engineering_only=True,
        skill=request.skill.model_dump(mode="json"),
        memory=request.memory.model_dump(mode="json"),
        max_generations=trace.max_generations,
        max_interactions=trace.max_interactions,
    )
    if ref.content_schema == "engineering-execution-policy/1":
        if value != expected:
            raise EvidenceIntegrityError("Original full-AX execution policy changed")
        return FullAxProjection()
    if set(value) != set(expected) | {"actor_projection"} or any(
        value[k] != v for k, v in expected.items()
    ):
        raise EvidenceIntegrityError(
            "Explicit Actor view policy fields changed or missing"
        )
    try:
        choice = actor_projection_configuration(value["actor_projection"])
        check_projection_task(choice, request.task.identity)
        return choice
    except (ValueError, TypeError) as error:
        raise EvidenceIntegrityError(
            "Unsupported or incomplete Actor projection selection"
        ) from error


def original_source_projection(
    request: ActorRunRequest,
    trace: TracePlan,
    store: EvidenceReader,
    control: OperationControl,
) -> ActorProjectionConfiguration:
    ref = trace.binding.run.plan_ref
    if (ref.content_schema, ref.visibility, ref.media_type) != (
        "run-plan/3",
        "private",
        "application/json",
    ) or not 0 < ref.size_bytes <= 1024**2:
        raise EvidenceIntegrityError("Original source execution RunPlan required")
    raw = store.read(ref, control=control)
    if len(raw) != ref.size_bytes or hashlib.sha256(raw).hexdigest() != ref.sha256:
        raise EvidenceIntegrityError("Source RunPlan bytes changed")
    run = RunPlan.model_validate_json(raw)
    if run.model_dump_json().encode() != raw or not isinstance(
        run.workload, ExecutionWorkload
    ):
        raise EvidenceIntegrityError(
            "Original canonical source execution plan required"
        )
    run.check_binding(trace.binding.run)
    if request.schema_version == "actor-run-request/2":
        config = actor_context_configuration(request, store, control)
        spec = actor_context_document(
            store,
            run.resources.configuration_ref,
            "actor-resource-spec/1",
            ActorResourceSpec,
            8 * 1024**2,
            control,
        )
        expected = freeze_actor_context(
            spec,
            request.parameters_refs,
            config.policy,
            store,
            soft_target=config.profiles[0].soft_target,
            control=control,
        )
        roles = run.models
        if (
            run.purpose != "engineering"
            or run.budget is not None
            or len(roles) != 1
            or roles[0].role != "actor"
            or roles[0].paid
            or roles[0].provider != "fixed-actor-worker"
            or roles[0].model != config.profiles[0].model
            or roles[0].model_binding_ref != spec.model_binding_ref
            or roles[0].parameters_ref != request.parameters_refs[0]
            or spec.token != request.model_allocation
            or spec.release_ref != run.release_ref
            or config != expected
        ):
            raise EvidenceIntegrityError(
                "Actor context differs from original run/model/resource pins"
            )
    return read_source_projection(
        run.workload.execution_policy_ref, request, trace, store, control
    )
