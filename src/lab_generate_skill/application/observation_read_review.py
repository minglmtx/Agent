"""Original captured read facts shared by closed Actor and permitted role review."""

from lab_generate_skill.actor.observation_read_response import parse_observation_read
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.domain.observation_read import ObservationReadPayload
from lab_generate_skill.domain.observation_viewport import (
    ObservationViewport,
    viewport_reference,
    MAX_VIEWPORT_BYTES,
)
from .verified_evidence_inputs import verified_input_document
from lab_generate_skill.domain.observation_read_return import ReturnedObservationRead
from lab_generate_skill.domain.trace import TraceTurn
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody
from lab_generate_skill.policies.observation_display import observation_read_body
from lab_generate_skill.policies.observation_index import (
    ObservationIndex,
    index_public_ax,
)
from lab_generate_skill.policies.observation_protection import (
    verify_observation_read_window,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .context_evidence import read_bytes


def review_observation_read(
    turn: TraceTurn,
    before: ResolvedObservation,
    prompt: ActorPrompt,
    completion: ActorTextCompletion | None,
    evidence: EvidenceReader,
    control: OperationControl,
    indices: dict[str, ObservationIndex],
) -> ObservationReadPayload | None:
    fact = turn.reading
    if fact is None:
        return None
    decision = turn.decision
    view = prompt.observation_view
    if (
        decision is None
        or decision.read_policy is None
        or view is None
        or completion is None
    ):
        raise OwnershipConflict(
            "Original read requires its completed proposal and declared actual input"
        )
    request = fact.request
    if (view.snapshot, view.policy) != (request.snapshot, decision.read_policy):
        raise OwnershipConflict(
            "Recorded read changed original snapshot/policy in actual Actor input"
        )
    parsed = parse_observation_read(
        completion.text, completion.finish_reason, prompt, request_id=request.request_id
    )
    if parsed != request:
        raise EvidenceIntegrityError(
            "Recorded read does not match the original native model proposal"
        )
    VerifiedEvidenceBody(
        request.snapshot.observation_ref, before.record.model_dump_json().encode()
    )
    if fact.result is None:
        return None
    reference = fact.result.result_ref
    raw = read_bytes(evidence, reference, 16 * 1024**2, control)
    if reference.visibility != "public" or reference.content_schema not in (
        "observation-read-result/1",
        "observation-read-result/2",
    ):
        raise EvidenceIntegrityError(
            "Recorded only consumes original public read results"
        )
    payload = ObservationReadPayload.model_validate_json(raw)
    if (
        payload.schema_version != reference.content_schema
        or payload.model_dump_json().encode() != raw
    ):
        raise EvidenceIntegrityError(
            "Recorded read result changed original canonical bytes"
        )
    returned = ReturnedObservationRead(
        result_ref=reference,
        payload=payload,
        body=observation_read_body(payload),
        count=fact.result.count,
    )
    if returned.record != fact.result or payload.request != request:
        raise EvidenceIntegrityError(
            "Recorded read changed original returned body/ranges/count binding"
        )
    key = request.snapshot.model_dump_json()
    index = indices.get(key)
    if index is None:
        viewport_ref = viewport_reference(before.record)
        viewport = None
        if viewport_ref is not None:
            viewport = verified_input_document(
                evidence, viewport_ref, ObservationViewport, MAX_VIEWPORT_BYTES, control
            )
            viewport.require_observation(before.record, before.text)
        index = index_public_ax(
            request.snapshot.observation_ref,
            before.record.model_dump_json().encode(),
            before,
            turn.generation.scope,
            decision.read_policy,
            viewport=viewport,
        )
        indices.clear()
        indices[key] = index
    if index.snapshot != request.snapshot:
        raise OwnershipConflict("Recorded read uses another original captured snapshot")
    verify_observation_read_window(index, payload)
    return payload
