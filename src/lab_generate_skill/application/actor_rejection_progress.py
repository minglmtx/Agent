"""Check durable rejected turns using their original saved input and response."""

import hashlib
from typing import TypeVar
from lab_generate_skill.domain.actor_prompt import (
    ActorPrompt,
    MAX_ACTOR_INPUT_BYTES,
    MAX_ACTOR_RESPONSE_BYTES,
)
from lab_generate_skill.domain.actor_response import (
    ActorTextCompletion,
    ActorParseFailure,
)
from lab_generate_skill.domain.actor_proposal_feedback import (
    ActorInvalidProposalProgress,
    ActorProposalFeedback,
)
from lab_generate_skill.domain.observation_read_policy import ObservationReadPolicy
from lab_generate_skill.policies.actor_proposal_identity import proposal_fingerprint
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.trace import TraceTurn
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.actor_rejected_proposal import (
    rejected_proposal_identity,
)

T = TypeVar("T", bound=Contract)


def _read_original(
    ref: EvidenceRef,
    model: type[T],
    store: EvidenceReader,
    control: OperationControl,
    maximum: int,
) -> T:
    if ref.media_type != "application/json" or not 0 < ref.size_bytes <= maximum:
        raise EvidenceIntegrityError("Rejected-proposal fact exceeds JSON boundary")
    raw = store.read(ref, control=control)
    if type(raw) is not bytes or (len(raw), hashlib.sha256(raw).hexdigest()) != (
        ref.size_bytes,
        ref.sha256,
    ):
        raise EvidenceIntegrityError("Rejected-proposal fact changed original bytes")
    result = model.model_validate_json(raw)
    if result.model_dump_json().encode() != raw:
        raise EvidenceIntegrityError("Rejected-proposal fact is not canonical")
    return result


class ActorRepeatedInvalidProposalsStopped(RuntimeError):
    reason_code = "ACTOR_REPEATED_INVALID_PROPOSALS"

    def __init__(self, turn: TraceTurn, signature: str, count: int, limit: int) -> None:
        self.generation_id = turn.generation.generation_id
        self.request_id = turn.generation.request_id
        self.snapshot_ref = turn.generation.before_observation_ref
        self.proposal_sha256 = signature
        self.count, self.limit = count, limit
        super().__init__(
            "Actor/decision-rejection: repeated invalid proposal stopped; "
            f"count={count}; limit={limit}; executed=false; generation={self.generation_id}; "
            f"request={self.request_id}; snapshot={self.snapshot_ref.sha256}"
        )


class ActorInvalidProposalsStopped(ActorRepeatedInvalidProposalsStopped):
    def __init__(
        self,
        turn: TraceTurn,
        progress: ActorInvalidProposalProgress,
        policy: ObservationReadPolicy,
    ) -> None:
        identical = progress.repeated_invalid >= (
            policy.max_identical_invalid_proposals or 0
        )
        self.reason_code = (
            "ACTOR_REPEATED_INVALID_PROPOSALS"
            if identical
            else "ACTOR_INVALID_PROPOSAL_LIMIT"
        )
        self.consecutive_invalid, self.repeated_invalid = (
            progress.consecutive_invalid,
            progress.repeated_invalid,
        )
        super().__init__(
            turn,
            progress.last_fingerprint or ("0" * 64),
            progress.repeated_invalid if identical else progress.consecutive_invalid,
            (
                policy.max_identical_invalid_proposals
                if identical
                else policy.max_consecutive_invalid_proposals
            )
            or 0,
        )


def invalid_proposal_progress(
    snapshot: TraceSnapshot,
    store: EvidenceReader,
    control: OperationControl,
    current_observation: EvidenceRef,
    *,
    policy: ObservationReadPolicy,
) -> ActorInvalidProposalProgress:
    consecutive = 0
    counts: dict[str, int] = {}
    last: str | None = None
    for turn in reversed(snapshot.project().turns):
        if turn.decision is None or turn.decision.outcome != "invalid":
            break
        generation = turn.generation
        if consecutive >= (policy.max_consecutive_invalid_proposals or 0):
            raise OwnershipConflict(
                "Rejected trace continued beyond its frozen consecutive limit"
            )
        if generation.response_ref is None or turn.decision.failure_ref is None:
            raise OwnershipConflict("Rejected progress lost original response/failure")
        control.checkpoint()
        prompt = _read_original(
            generation.input_ref, ActorPrompt, store, control, MAX_ACTOR_INPUT_BYTES
        )
        completion = _read_original(
            generation.response_ref,
            ActorTextCompletion,
            store,
            control,
            MAX_ACTOR_RESPONSE_BYTES,
        )
        failure = _read_original(
            turn.decision.failure_ref,
            ActorParseFailure,
            store,
            control,
            MAX_ACTOR_RESPONSE_BYTES,
        )
        if (
            completion.generation_id,
            completion.request_id,
            completion.input_ref,
            completion.parameters_ref,
            completion.model_input_sha256,
            failure.generation_id,
            failure.response_ref,
        ) != (
            generation.generation_id,
            generation.request_id,
            generation.input_ref,
            generation.parameters_ref,
            hashlib.sha256(prompt.input_bytes()).hexdigest(),
            generation.generation_id,
            generation.response_ref,
        ):
            raise OwnershipConflict(
                "Rejected progress changed original generation/failure"
            )
        view = prompt.observation_view
        if (
            view is None
            or view.policy != policy
            or (view.snapshot.scope, view.snapshot.observation_ref)
            != (generation.scope, generation.before_observation_ref)
        ):
            raise OwnershipConflict(
                "New rejected progress changed frozen policy/snapshot"
            )
        feedback = ActorProposalFeedback.model_validate_json(failure.message)
        consecutive += 1
        if generation.before_observation_ref == current_observation:
            signature = proposal_fingerprint(prompt, completion, feedback.code)
            counts[signature] = counts.get(signature, 0) + 1
            if consecutive == 1:
                last = signature
        control.checkpoint()
    return ActorInvalidProposalProgress(
        consecutive_invalid=consecutive,
        repeated_invalid=counts[last] if last is not None else 0,
        last_fingerprint=last,
        fingerprints=tuple(sorted(counts.items())),
    )


class RecordedActorRejectionProgress:
    def __init__(self, evidence: EvidenceReader) -> None:
        self.evidence = evidence

    def derive(
        self,
        snapshot: TraceSnapshot,
        current_observation: EvidenceRef,
        policy: ObservationReadPolicy,
        *,
        control: OperationControl,
        inputs: EvidenceReader | None = None,
    ) -> ActorInvalidProposalProgress:
        return invalid_proposal_progress(
            snapshot,
            self.evidence if inputs is None else inputs,
            control,
            current_observation,
            policy=policy,
        )


def check_repeated_invalid_proposals(
    snapshot: TraceSnapshot, store: EvidenceReader, control: OperationControl
) -> None:
    turns = snapshot.project().turns
    signature: str | None = None
    count = 0
    limit = 0
    for turn in reversed(turns):
        if turn.decision is None or turn.decision.outcome != "invalid":
            break  # A valid action/read ends the rejected-proposal streak.
        generation = turn.generation
        assert generation.response_ref is not None
        control.checkpoint()
        prompt = _read_original(
            generation.input_ref, ActorPrompt, store, control, MAX_ACTOR_INPUT_BYTES
        )
        if (
            prompt.observation_view is not None
            and prompt.observation_view.policy.schema_version
            == "observation-read-policy/2"
        ):
            policy = prompt.observation_view.policy
            progress = invalid_proposal_progress(
                snapshot,
                store,
                control,
                generation.before_observation_ref,
                policy=policy,
            )
            if progress.consecutive_invalid >= (
                policy.max_consecutive_invalid_proposals or 0
            ) or progress.repeated_invalid >= (
                policy.max_identical_invalid_proposals or 0
            ):
                raise ActorInvalidProposalsStopped(turns[-1], progress, policy)
            return
        completion = _read_original(
            generation.response_ref,
            ActorTextCompletion,
            store,
            control,
            MAX_ACTOR_RESPONSE_BYTES,
        )
        if (
            completion.generation_id,
            completion.request_id,
            completion.input_ref,
            completion.parameters_ref,
            completion.model_input_sha256,
        ) != (
            generation.generation_id,
            generation.request_id,
            generation.input_ref,
            generation.parameters_ref,
            hashlib.sha256(prompt.input_bytes()).hexdigest(),
        ):
            raise OwnershipConflict(
                "Rejected-proposal progress changed original completion"
            )
        view = prompt.observation_view
        if view is None or not view.tools:
            break
        if (view.snapshot.scope, view.snapshot.observation_ref) != (
            generation.scope,
            generation.before_observation_ref,
        ):
            raise OwnershipConflict(
                "Rejected-proposal progress changed original public snapshot"
            )
        current = rejected_proposal_identity(prompt, completion)
        if signature is None:
            signature = current
            limit = view.policy.consecutive_no_progress
        if current != signature:
            break
        count += 1
        control.checkpoint()
        if count >= limit:
            assert signature is not None
            raise ActorRepeatedInvalidProposalsStopped(
                turns[-1], signature, count, limit
            )
