"""Read-only engineering review of original model/public inputs/browser facts.

No live handles, replay, model load, journal mutation or source admission. The
separate native reviewer also checks original resource and restoration evidence.
"""

import hashlib
from lab_generate_skill.policies.actor_parse_failure import (
    same_parse_failure,
    REJECTION_PREFIX,
)
from lab_generate_skill.ports.actor import ActorProjection
from lab_generate_skill.ports.actor_context import (
    ActorContextInputReview,
    ActorObservationReadReview,
    ActorObservationProposalReview,
)
from lab_generate_skill.actor.response import parse_actor_action
from lab_generate_skill.actor.schema_response import NEW_PROMPTS, parse_schema_proposal
from lab_generate_skill.actor.proposal_correction import corrective_proposal_feedback
from lab_generate_skill.domain.actor_proposal_feedback import ActorProposalError
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.observation_read import ObservationReadRequest
from lab_generate_skill.actor.observation_read_response import parse_observation_read
from lab_generate_skill.application.actor_loop_inputs import prepare_turn
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.models.actor_execution_evidence import verify_execution
from lab_generate_skill.adapters.models.local_actor_evidence import ActorEvidence
from lab_generate_skill.domain.actor_run import ActorRunRequest, ActorStop
from lab_generate_skill.domain.actor_response import (
    ActorTextCompletion,
    ActorParseFailure,
)
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_events import GenerationPlanned
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.domain.lifecycle import OperationContext
from typing import TypeVar

T = TypeVar("T", bound=Contract)


def read_fact(
    store: EvidenceStore, ref: EvidenceRef, model: type[T], control: OperationControl
) -> T:
    if (
        ref.media_type != "application/json"
        or not 0 < ref.size_bytes <= 16 * 1024 * 1024
    ):
        raise EvidenceIntegrityError("Review fact outside JSON boundary")
    raw = store.read(ref, control=control)
    if (len(raw), hashlib.sha256(raw).hexdigest()) != (ref.size_bytes, ref.sha256):
        raise EvidenceIntegrityError("Review bytes differ from original reference")
    value = model.model_validate_json(raw)
    if raw != value.model_dump_json().encode():
        raise EvidenceIntegrityError("Review fact is not canonical")
    return value


def review_actor(
    request: ActorRunRequest,
    snapshot: TraceSnapshot,
    executions: tuple[LocalActorExecution, ...],
    store: EvidenceStore,
    controls: OperationControls,
    operation: OperationContext,
    *,
    project: ActorProjection | None = None,
    context: ActorContextInputReview | None = None,
) -> dict[str, int | str]:
    control = controls.bind(operation)
    if (request.schema_version == "actor-run-request/2") != (context is not None):
        raise EvidenceIntegrityError(
            "Review requires the original context version and verifier"
        )
    trace = snapshot.project().sealed
    if trace is None or trace.stop_reason in ("error", "cancelled", "uncertain"):
        raise EvidenceIntegrityError("No complete Actor attempt to review")
    if (
        request.scope,
        request.initial_observation_ref,
        len(request.parameters_refs),
    ) != (
        snapshot.plan.scope,
        snapshot.plan.initial_observation_ref,
        snapshot.plan.max_generations,
    ):
        raise EvidenceIntegrityError("Review request differs from original trace")
    if len(executions) != trace.completed_generations or len(
        {x.call.intent.generation_id for x in executions}
    ) != len(executions):
        raise EvidenceIntegrityError("Missing or duplicate actual model exchanges")
    expected = {x.call.intent.generation_id: x for x in executions}
    observations = EvidenceObservations(store, controls)
    prompts = {}
    proposals: dict[
        str, BrowserAction | ObservationReadRequest | ActorProposalError
    ] = {}
    for i, event in enumerate(snapshot.events):
        if not isinstance(event, GenerationPlanned):
            continue
        intent = event.intent
        prefix = TraceSnapshot.model_validate(
            snapshot.model_copy(update={"events": snapshot.events[:i]})
        )
        index = len(prefix.project().turns)
        if intent.parameters_ref != request.parameters_refs[index]:
            raise EvidenceIntegrityError(
                "Review model parameters changed original turn"
            )
        if context is None:
            if project is None:
                raise EvidenceIntegrityError(
                    "Legacy input review requires its original explicit projector"
                )
            prompt = prepare_turn(
                request, prefix, operation, control, store, observations, project
            )
        else:
            prompt = context.verify(request, prefix, intent, operation, control=control)
        if prompt.model_dump_json().encode() != store.read(
            intent.input_ref, control=control
        ):
            raise EvidenceIntegrityError(
                "Review prompt differs from public original trace"
            )
        prompts[intent.generation_id] = prompt
        execution = expected.get(intent.generation_id)
        if (
            execution is None
            or execution.call.intent != intent
            or execution.call.binding.resource != request.model_allocation
        ):
            raise EvidenceIntegrityError(
                "Review exchange lacks original resource/intent"
            )
        verify_execution(ActorEvidence(store), execution, control)
        if prompt.prompt_version in NEW_PROMPTS:
            completion = read_fact(
                store, execution.response_ref, ActorTextCompletion, control
            )
            try:
                proposal = parse_schema_proposal(
                    completion.text,
                    completion.finish_reason,
                    request.task,
                    prompt,
                    action_id="action-"
                    + hashlib.sha256(intent.generation_id.encode()).hexdigest(),
                    request_id="read-"
                    + hashlib.sha256(intent.generation_id.encode()).hexdigest(),
                )
                if not isinstance(proposal, BrowserAction):
                    if not isinstance(context, ActorObservationProposalReview):
                        raise EvidenceIntegrityError(
                            "Original typed-read proposal verifier is missing"
                        )
                    context.verify_proposal(
                        prompt, proposal, operation, control=control
                    )
                proposals[intent.generation_id] = proposal
            except ActorProposalError as error:
                proposals[intent.generation_id] = error
    for turn in trace.turns:
        gen, decision, interaction = turn.generation, turn.decision, turn.interaction
        if gen.status != "completed" or gen.response_ref is None or decision is None:
            raise EvidenceIntegrityError("Review requires complete generation/decision")
        execution = expected[gen.generation_id]
        if execution.response_ref != gen.response_ref:
            raise EvidenceIntegrityError("Review response changed recorded generation")
        completion = read_fact(store, gen.response_ref, ActorTextCompletion, control)
        prompt = prompts[gen.generation_id]
        new_proposal = proposals.get(gen.generation_id)
        if prompt.prompt_version in NEW_PROMPTS:
            if isinstance(new_proposal, ActorProposalError):
                if decision.outcome != "invalid" or decision.failure_ref is None:
                    raise EvidenceIntegrityError("Typed proposal rejection was hidden")
                failure = read_fact(
                    store, decision.failure_ref, ActorParseFailure, control
                )
                feedback = corrective_proposal_feedback(
                    new_proposal, prompt, completion, request.task
                )
                if (
                    failure.generation_id,
                    failure.response_ref,
                    failure.error_type,
                    failure.message,
                ) != (
                    gen.generation_id,
                    gen.response_ref,
                    "ActorProposalError",
                    feedback.model_dump_json(),
                ):
                    raise EvidenceIntegrityError(
                        "Typed proposal feedback changed original policy/input/progress"
                    )
                continue
            if new_proposal is None or decision.outcome == "invalid":
                raise EvidenceIntegrityError(
                    "Valid typed proposal was changed to a rejection"
                )
            if isinstance(new_proposal, BrowserAction):
                if decision.outcome != "action":
                    raise EvidenceIntegrityError("Typed action changed decision branch")
            elif decision.outcome != "read" or decision.read_request != new_proposal:
                raise EvidenceIntegrityError(
                    "Typed read changed original request or branch"
                )
        if decision.outcome == "read":
            if turn.reading is None or not isinstance(
                context, ActorObservationReadReview
            ):
                raise EvidenceIntegrityError(
                    "Original closed read-event verifier is missing"
                )
            context.verify_reading(
                request,
                turn,
                prompts[gen.generation_id],
                completion,
                operation,
                control=control,
            )
            continue
        if isinstance(new_proposal, BrowserAction):
            action = new_proposal
        else:
            try:
                reading = parse_observation_read(
                    completion.text,
                    completion.finish_reason,
                    prompts[gen.generation_id],
                    request_id="read-"
                    + hashlib.sha256(gen.generation_id.encode()).hexdigest(),
                )
                if reading is not None:
                    raise EvidenceIntegrityError(
                        "Review found a read proposal hidden as action/invalid"
                    )
                action = parse_actor_action(
                    completion.text,
                    completion.finish_reason,
                    request.task,
                    "action-" + hashlib.sha256(gen.generation_id.encode()).hexdigest(),
                )
            except (ValueError, TypeError, SyntaxError, RecursionError) as error:
                if decision.outcome != "invalid" or decision.failure_ref is None:
                    raise EvidenceIntegrityError(
                        "Review invalid decision was hidden"
                    ) from error
                failure = read_fact(
                    store, decision.failure_ref, ActorParseFailure, control
                )
                if (
                    failure.generation_id,
                    failure.response_ref,
                    failure.error_type,
                ) != (
                    gen.generation_id,
                    gen.response_ref,
                    type(error).__name__,
                ) or not same_parse_failure(
                    failure.error_type,
                    failure.message.removeprefix(REJECTION_PREFIX),
                    error,
                ):
                    raise EvidenceIntegrityError(
                        "Review parse failure changed original result"
                    )
                continue
        if (
            action != decision.action
            or interaction is None
            or interaction.result is None
        ):
            raise EvidenceIntegrityError(
                "Review action differs from actual parsed response"
            )
        result = interaction.result
        raw = read_fact(store, result.return_ref, BrowserReadout, control)
        after = read_fact(store, result.observation_ref, Observation, control)
        before = read_fact(store, result.before_observation_ref, Observation, control)
        if (raw.scope, raw.operation, raw.action, raw.observation) != (
            trace.scope,
            interaction.operation,
            action,
            after,
        ):
            raise EvidenceIntegrityError(
                "Review browser return changed actual interaction"
            )
        if after.sequence != before.sequence + 1 or result.terminal != (
            raw.terminated or raw.truncated or raw.protocol_terminal
        ):
            raise EvidenceIntegrityError("Review browser sequence/terminal differs")
    stop = read_fact(store, trace.stop_evidence_ref, ActorStop, control)
    original_request = read_fact(store, stop.request_ref, ActorRunRequest, control)
    if original_request != request or (
        stop.scope,
        stop.reason,
        stop.generations,
        stop.interactions,
        stop.final_observation_ref,
    ) != (
        trace.scope,
        trace.stop_reason,
        trace.generations,
        trace.interactions,
        trace.final_observation_ref,
    ):
        raise EvidenceIntegrityError("Review stop differs from actual sealed trace")
    return dict(
        generations=trace.generations,
        interactions=trace.interactions,
        stop_reason=trace.stop_reason,
    )
