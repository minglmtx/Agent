"""Closed captured-read/native-token proof; no live model, permission or replay."""

from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.actor_proposal_feedback import (
    ActorInvalidProposalProgress,
)
from lab_generate_skill.domain.observation_read_geometry import (
    reading_progress_fingerprint,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation_read import ObservationReadPayload
from lab_generate_skill.domain.trace import TraceTurn
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.policies.observation_display import observation_read_body
from lab_generate_skill.policies.observation_index import ObservationIndex
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.observations import Observations
from lab_generate_skill.ports.context_projection import ContextCountEvidenceVerifier
from lab_generate_skill.ports.lifecycle import OperationControl
from .verified_evidence_inputs import verified_input_document
from .observation_read_review import review_observation_read


def review_actor_read(
    request: ActorRunRequest,
    turn: TraceTurn,
    prompt: ActorPrompt,
    completion: ActorTextCompletion,
    operation: OperationContext,
    configuration: ActorContextConfiguration,
    evidence: EvidenceReader,
    observations: Observations,
    counts: ContextCountEvidenceVerifier,
    indices: dict[str, ObservationIndex],
    control: OperationControl,
) -> ObservationReadPayload:
    fact = turn.reading
    projection = configuration.policy.actor_projection
    if (
        fact is None
        or fact.scope != request.scope
        or not isinstance(projection, AdaptiveObservationProjection)
        or not projection.supports_local(request.scope.task)
    ):
        raise OwnershipConflict(
            "Original task has no qualified declared reading capability"
        )
    before = observations.load(turn.generation.before_observation_ref, operation)
    payload = review_observation_read(
        turn, before, prompt, completion, evidence, control, indices
    )
    if payload is None or fact.result is None or fact.outcome != "returned":
        raise EvidenceIntegrityError(
            "Complete Actor review requires a confirmed original reading result"
        )
    counted = fact.result.count
    measured = counts.verify(
        counted, configuration.profiles[0], configuration.policy, control=control
    )
    if measured != counted.measurement:
        raise EvidenceIntegrityError(
            "Read native counter returned another original measurement"
        )
    private_state_ref(measured.input_ref, "actor-model-input/1")
    probe = verified_input_document(
        evidence, measured.input_ref, ActorPrompt, 8 * 1024**2, control
    )
    body = observation_read_body(payload)
    view = probe.observation_view
    if (
        probe.prompt_version
        != (
            "browsergym-adaptive-count-probe-v2"
            if projection.read_policy.schema_version == "observation-read-policy/2"
            else "browsergym-adaptive-count-probe-v1"
        )
        or view is None
        or (
            view.snapshot,
            view.policy,
            view.source_spans,
            view.body_start,
            view.body_end,
            probe.messages[1].content,
            view.read_result_ref,
        )
        != (
            fact.request.snapshot,
            projection.read_policy,
            payload.covered_ranges,
            0,
            len(body),
            body,
            None,
        )
    ):
        raise EvidenceIntegrityError(
            "Read count probe is not the exact original complete public body"
        )
    if (
        view.mode,
        view.body_token_limit,
        view.tools,
        view.reads_used,
        view.no_progress,
        view.omissions,
    ) != (
        "local",
        projection.read_policy.body_max_tokens,
        ("list_regions", "read_region", "search_regions"),
        0,
        0,
        ("count_probe_only",),
    ):
        raise EvidenceIntegrityError(
            "Read native probe changed its frozen count-only contract"
        )
    if projection.read_policy.schema_version == "observation-read-policy/2":
        if (
            payload.overview is None
            or view.schema_version != "actor-observation-view/3"
            or view.tab_count != len(payload.overview.tabs)
            or view.invalid_proposals != ActorInvalidProposalProgress()
            or view.progress_fingerprint != reading_progress_fingerprint(payload)
        ):
            raise EvidenceIntegrityError(
                "Read count probe changed original tab/progress/zero-rejection facts"
            )
    if (
        view.body(probe.messages[1].content) != body
        or measured.observation_tokens is None
        or measured.observation_tokens
        > min(fact.request.output_tokens, projection.read_policy.body_max_tokens)
    ):
        raise EvidenceIntegrityError(
            "Original native read body exceeds its bound or changed source"
        )
    control.checkpoint()
    return payload
