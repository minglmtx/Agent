"""Readonly reuse of original Actor projection, bounded by the evaluator control."""

import hashlib
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_prompt import ActorPrompt, MAX_ACTOR_INPUT_BYTES
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_events import GenerationPlanned
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.plans.observations import ObservationReader
from lab_generate_skill.application.actor_loop_inputs import prepare_turn
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.evaluators.evidence import EvaluationEvidence


class _HistoricalObservations:
    def __init__(
        self,
        reader: EvidenceReader,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self.reader, self.operation, self.control = (
            ObservationReader(reader),
            operation,
            control,
        )

    def load(self, reference: EvidenceRef, op: OperationContext) -> ResolvedObservation:
        if op != self.operation:
            raise EvidenceIntegrityError(
                "Issued AX read changed original historical operation"
            )
        return self.reader.load(reference, self.control)


def last_issued_ax(
    request: ActorRunRequest,
    snapshot: TraceSnapshot,
    trace: InteractionTrace,
    reader: EvidenceReader,
    control: OperationControl,
) -> str:
    request = ActorRunRequest.model_validate(request)
    snapshot = TraceSnapshot.model_validate(snapshot)
    trace = InteractionTrace.model_validate(trace)
    control.checkpoint()
    if (
        snapshot.project().sealed != trace
        or trace.stop_reason in ("error", "uncertain", "cancelled")
        or (
            request.scope,
            request.initial_observation_ref,
            len(request.parameters_refs),
        )
        != (
            snapshot.plan.scope,
            snapshot.plan.initial_observation_ref,
            snapshot.plan.max_generations,
        )
    ):
        raise EvidenceIntegrityError(
            "Issued AX requires original complete sealed Actor attempt"
        )
    planned = [
        (i, e)
        for i, e in enumerate(snapshot.events)
        if isinstance(e, GenerationPlanned)
    ]
    if len(planned) != len(trace.turns):
        raise EvidenceIntegrityError("Issued AX planned/completed turn count differs")
    if not planned:
        return ""
    index, event = planned[-1]
    generation = trace.turns[-1].generation
    if (
        generation.status != "completed"
        or generation.response_ref is None
        or generation.parameters_ref != request.parameters_refs[len(planned) - 1]
    ):
        raise EvidenceIntegrityError("Last AX has no original completed generation")
    prefix = TraceSnapshot.model_validate(
        snapshot.model_copy(update={"events": snapshot.events[:index]})
    )
    # Operation is only a historical identity here. Actual reads use the caller's
    # current bounded control; no expired request deadline becomes new authority.
    observations = _HistoricalObservations(reader, request.operation, control)
    expected = prepare_turn(
        request, prefix, request.operation, control, reader, observations, prepare_actor
    )
    evidence = EvaluationEvidence(reader, control)
    prompt = evidence.read(
        generation.input_ref,
        "actor-model-input/1",
        ActorPrompt,
        limit=MAX_ACTOR_INPUT_BYTES,
    )
    completion = evidence.read(
        generation.response_ref, "actor-model-response/1", ActorTextCompletion
    )
    if prompt != expected or (
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
        raise EvidenceIntegrityError(
            "Issued AX differs from original projected input/completed request"
        )
    if (
        event.intent.before_observation_ref != generation.before_observation_ref
        or event.intent.scope != request.scope
    ):
        raise EvidenceIntegrityError("Issued AX changed original observation scope")
    actual = observations.load(generation.before_observation_ref, request.operation)
    if actual.text is None:
        raise EvidenceIntegrityError("Last issued AX text unavailable")
    control.checkpoint()
    return actual.text
