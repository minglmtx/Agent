"""Exact public turn reconstruction and CAS publication for the Actor loop."""

import hashlib
from typing import TypeVar
from lab_generate_skill.domain.actor_prompt import (
    ActorHistoryItem,
    ActorPublicTurn,
    ActorPrompt,
    MAX_ACTOR_RESPONSE_BYTES,
)
from lab_generate_skill.domain.actor_response import (
    ActorTextCompletion,
    ActorParseFailure,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest, ActorStop
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.ports.actor import ActorProjection
from lab_generate_skill.ports.evidence import EvidenceStore, EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.observations import ObservationLoader

T = TypeVar("T", bound=Contract)


def put_actor_fact(
    value: ActorRunRequest | ActorPrompt | ActorStop,
    store: EvidenceStore,
    control: OperationControl,
) -> EvidenceRef:
    raw = value.model_dump_json().encode()
    metadata = EvidenceMetadata(
        media_type="application/json",
        content_schema=value.schema_version,
        visibility="private",
        producer="actor-loop-v1",
    )
    candidate = evidence_reference(raw, metadata)
    returned: EvidenceRef | None = None
    try:
        returned = EvidenceRef.model_validate(store.put(raw, metadata, control=control))
        if returned.model_dump(exclude={"uri"}) != candidate.model_dump(
            exclude={"uri"}
        ):
            raise EvidenceIntegrityError(
                "Actor loop publication changed original bytes/metadata"
            )
        control.checkpoint()
        return returned
    except BaseException as error:
        setattr(error, "actor_fact_candidate", candidate)
        setattr(error, "actor_fact_reference", returned)
        raise


def _read(
    ref: EvidenceRef, model: type[T], store: EvidenceReader, control: OperationControl
) -> T:
    if (
        ref.media_type != "application/json"
        or not 0 < ref.size_bytes <= MAX_ACTOR_RESPONSE_BYTES
    ):
        raise EvidenceIntegrityError("Actor history fact exceeds JSON boundary")
    raw = store.read(ref, control=control)
    if len(raw) != ref.size_bytes or hashlib.sha256(raw).hexdigest() != ref.sha256:
        raise EvidenceIntegrityError("Actor history changed original bytes")
    value = model.model_validate_json(raw)
    if value.model_dump_json().encode() != raw:
        raise EvidenceIntegrityError("Actor history requires canonical original facts")
    return value


def public_turn(
    request: ActorRunRequest,
    snapshot: TraceSnapshot,
    operation: OperationContext,
    control: OperationControl,
    store: EvidenceReader,
    observations: ObservationLoader,
) -> ActorPublicTurn:
    view = snapshot.project()
    current = observations.load(view.current_observation(snapshot.plan), operation)
    actual = current.record
    if (actual.task, actual.context_id, actual.attempt_id) != (
        request.scope.task,
        request.scope.context_id,
        request.scope.attempt_id,
    ):
        raise OwnershipConflict("Actor current observation changed original scope")
    history: list[ActorHistoryItem] = []
    for turn in view.turns:
        generation = turn.generation
        if (
            generation.status != "completed"
            or generation.response_ref is None
            or turn.decision is None
        ):
            raise ValueError(
                "Interrupted generation cannot precede a new Actor request"
            )
        if turn.decision.outcome == "read":
            if turn.reading is None or turn.reading.outcome != "returned":
                raise ValueError(
                    "Unconfirmed read cannot precede another Actor request"
                )
            # Actual reading proposals/returns remain in the original trace.
            # They are not invented browser actions in the legacy action history.
            continue
        if turn.decision.outcome == "invalid":
            assert turn.decision.failure_ref is not None
            response = _read(
                generation.response_ref, ActorTextCompletion, store, control
            )
            failure = _read(
                turn.decision.failure_ref, ActorParseFailure, store, control
            )
            if (
                response.generation_id,
                response.request_id,
                response.input_ref,
                response.parameters_ref,
                failure.generation_id,
                failure.response_ref,
            ) != (
                generation.generation_id,
                generation.request_id,
                generation.input_ref,
                generation.parameters_ref,
                generation.generation_id,
                generation.response_ref,
            ):
                raise OwnershipConflict(
                    "Actor invalid-response history changed original generation"
                )
            history.append(
                ActorHistoryItem(
                    schema_version=(
                        "actor-history-item/2"
                        if request.schema_version == "actor-run-request/2"
                        else None
                    ),
                    executed=(
                        False
                        if request.schema_version == "actor-run-request/2"
                        else None
                    ),
                    action=response.text,
                    error=failure.message,
                )
            )
        else:
            event = turn.interaction
            if event is None or event.result is None or event.result.terminal:
                raise ValueError(
                    "Unconfirmed/terminal action cannot precede a new Actor request"
                )
            after = observations.load(event.result.observation_ref, operation)
            history.append(
                ActorHistoryItem(
                    schema_version=(
                        "actor-history-item/2"
                        if request.schema_version == "actor-run-request/2"
                        else None
                    ),
                    executed=(
                        True
                        if request.schema_version == "actor-run-request/2"
                        else None
                    ),
                    action=event.action.payload,
                    error=after.record.last_action_error,
                )
            )
    public = ActorPublicTurn(
        task=request.task,
        skill=request.skill,
        observation=current,
        history=tuple(history),
        memory=request.memory,
    )
    return public


def prepare_turn(
    request: ActorRunRequest,
    snapshot: TraceSnapshot,
    operation: OperationContext,
    control: OperationControl,
    store: EvidenceReader,
    observations: ObservationLoader,
    project: ActorProjection,
) -> ActorPrompt:
    return ActorPrompt.model_validate(
        project(public_turn(request, snapshot, operation, control, store, observations))
    )


def actor_operation_id(original: str, label: str) -> str:
    return "actor-" + hashlib.sha256((original + ":" + label).encode()).hexdigest()
