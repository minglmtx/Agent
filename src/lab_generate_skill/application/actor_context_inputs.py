"""Original public turn/config/IDs shared by preparation and read-only admission."""

from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.context_preparation import ContextPreparationRequest
from lab_generate_skill.domain.context_projection import ActorContextSource
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.actor_context import ActorObservationSources
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from .actor_loop_inputs import public_turn, actor_operation_id
from .verified_evidence_inputs import verified_input_document

PUBLIC_ACTOR_CONTEXT = EvidenceMetadata(
    media_type="application/json",
    content_schema="actor-public-turn/1",
    visibility="public",
    producer="actor-context-input-v1",
)


def actor_context_configuration(
    request: ActorRunRequest, evidence: EvidenceReader, control: OperationControl
) -> ActorContextConfiguration:
    if (
        request.schema_version != "actor-run-request/2"
        or request.context_configuration_ref is None
    ):
        raise OwnershipConflict(
            "Explicit original Actor context configuration required"
        )
    reference = request.context_configuration_ref
    if reference.media_type != "application/json":
        raise EvidenceIntegrityError("Complete Actor context JSON required")
    config = verified_input_document(
        evidence, reference, ActorContextConfiguration, 16 * 1024**2, control
    )
    if tuple(p.configuration_ref for p in config.profiles) != request.parameters_refs:
        raise EvidenceIntegrityError(
            "Actor context configuration changed original per-turn parameters"
        )
    return config


def actor_public_fact(
    request: ActorRunRequest,
    before: TraceSnapshot,
    operation: OperationContext,
    evidence: EvidenceReader,
    observations: ObservationLoader,
    control: OperationControl,
    *,
    sources: ActorObservationSources | None = None,
    recorded: ActorPublicTurn | None = None,
) -> tuple[bytes, EvidenceRef]:
    turn = public_turn(request, before, operation, control, evidence, observations)
    if sources is not None:
        if recorded is None:
            turn = sources.prepare_public_source(
                request, before, operation, turn, control=control, inputs=evidence
            )
        else:
            sources.verify_public_source(
                request, before, operation, turn, recorded, control=control
            )
            turn = recorded
    elif recorded is not None:
        raise OwnershipConflict(
            "Recorded adaptive source has no original source verifier"
        )
    raw = turn.model_dump_json().encode()
    metadata = PUBLIC_ACTOR_CONTEXT.model_copy(
        update={"content_schema": turn.schema_version}
    )
    return raw, evidence_reference(raw, metadata)


def original_context_request(
    request: ActorRunRequest,
    before: TraceSnapshot,
    operation: OperationContext,
    request_id: str,
    source_ref: EvidenceRef,
    config: ActorContextConfiguration,
    *,
    active_read_ref: EvidenceRef | None = None,
) -> ContextPreparationRequest:
    view = before.project()
    index = len(view.turns)
    if (
        request.schema_version != "actor-run-request/2"
        or request.candidate_id is None
        or request.revision_round is None
        or before.plan.scope != request.scope
        or before.plan.initial_observation_ref != request.initial_observation_ref
        or before.plan.max_generations != len(request.parameters_refs)
        or view.sealed is not None
        or view.halted
        or view.intent is not None
        or view.generation is not None
        or view.action is not None
        or index >= before.plan.max_generations
        or view.interactions >= before.plan.max_interactions
    ):
        raise OwnershipConflict(
            "Context preparation is not the next original Actor turn"
        )
    prefix = f"turn-{index}"
    if (
        request_id
        != actor_operation_id(request.operation.operation_id, prefix + "-request")
        or operation.operation_id
        != actor_operation_id(request.operation.operation_id, prefix + "-generate")
        or operation.mode != "execute"
        or operation.deadline > request.operation.deadline
        or (operation.allocation_id, operation.recovery_ref)
        != (
            request.model_allocation.allocation_id,
            request.model_allocation.recovery_ref,
        )
    ):
        raise OwnershipConflict(
            "Context preparation changed original request/operation/resource"
        )
    source_fields: dict[str, object] = {}
    if source_ref.content_schema == "actor-public-turn/2":
        source_fields["active_read_ref"] = active_read_ref
    return ContextPreparationRequest(
        scope=request.scope,
        operation=operation,
        request_id=request_id,
        source=ActorContextSource.model_validate(
            dict(
                scope=request.scope,
                candidate_id=request.candidate_id,
                revision_round=request.revision_round,
                turn_ref=source_ref,
            )
            | source_fields
        ),
        profile=config.profiles[index],
        policy=config.policy,
    )
