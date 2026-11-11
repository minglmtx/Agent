"""Read and cross-bind original Actor inputs/returns; never rerun a request."""

from typing import TypeVar
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_response import (
    ActorTextCompletion,
    ActorParseFailure,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest, ActorStop
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.evaluation import Evaluation
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.observation import Observation, ResolvedObservation
from lab_generate_skill.domain.teacher_attempt import TeacherAttemptInput
from lab_generate_skill.domain.teacher_actor_material import (
    TeacherActorMaterial,
    TeacherActorTurn,
)
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.teacher_json import MAX_TEACHER_BYTES
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.ports.traces import TraceRecords
from lab_generate_skill.domain.lifecycle import OperationContext
from .context_evidence import read_bytes
from .teacher_observation_reads import teacher_observation_read
from lab_generate_skill.policies.observation_index import ObservationIndex
from lab_generate_skill.policies.observation_display import observation_read_body
import hashlib

T = TypeVar("T", bound=Contract)


def canonical(
    ref: EvidenceRef,
    schema: str,
    model: type[T],
    evidence: EvidenceReader,
    control: OperationControl,
    limit: int = 16 * 1024**2,
    *,
    public: bool = False,
) -> T:
    if (ref.content_schema, ref.visibility, ref.media_type) != (
        schema,
        "public" if public else "private",
        "application/json",
    ):
        raise EvidenceIntegrityError("Original leaf schema/visibility changed")
    raw = read_bytes(evidence, ref, limit, control)
    value = model.model_validate_json(raw)
    if value.model_dump_json().encode() != raw:
        raise EvidenceIntegrityError(
            "Original Actor leaf must retain canonical complete bytes"
        )
    return value


def read_actor_material(
    original: TeacherAttemptInput,
    evidence: EvidenceReader,
    observations: ObservationLoader,
    traces: TraceRecords,
    operation: OperationContext,
    *,
    control: OperationControl,
) -> TeacherActorMaterial:
    original = TeacherAttemptInput.model_validate(original)
    op = OperationContext.model_validate(operation)
    parent = original.operation
    if op != parent and not (
        op.mode == "cleanup"
        and op.parent_operation_id == parent.operation_id
        and (op.run_id, op.owner_id, op.attempt_id, op.allocation_id, op.recovery_ref)
        == (parent.run_id, parent.owner_id, None, None, None)
    ):
        raise OwnershipConflict(
            "Native Teacher read requires original command or parent cleanup"
        )
    control.checkpoint()
    request = canonical(
        original.actor_request_ref,
        original.actor_request_ref.content_schema,
        ActorRunRequest,
        evidence,
        control,
    )
    recorded_trace = canonical(
        original.trace_ref, "interaction-trace/1", InteractionTrace, evidence, control
    )
    # Bound the native source graph before TraceRecords resolves page bodies.
    # This is a format admission bound, never truncation or a task judgment.
    refs: dict[str, EvidenceRef] = {}

    def bounded(values: object) -> None:
        for ref in evidence_references(values):
            refs[ref.model_dump_json()] = ref
        if sum(ref.size_bytes for ref in refs.values()) > 256 * 1024**2:
            raise ValueError(
                "Native Teacher source dependency graph exceeds its bounded 256MiB read format"
            )

    bounded(recorded_trace)
    public_records: dict[str, Observation] = {}
    for ref in tuple(refs.values()):
        if ref.content_schema == "observation/1" and ref.visibility == "public":
            record = canonical(
                ref, "observation/1", Observation, evidence, control, public=True
            )
            if record.artifacts:
                raise ValueError(
                    "Text Teacher attempt requires explicit artifact support; do not omit artifacts"
                )
            public_records[ref.model_dump_json()] = record
            bounded(record)
    trace = traces.load(original.trace_ref, op)
    # The port verifies original provenance; compare its return to actual bytes.
    if trace != recorded_trace:
        raise EvidenceIntegrityError("Trace port changed original sealed bytes")
    evaluation = canonical(
        original.evaluation_ref,
        "evaluation/1",
        Evaluation,
        evidence,
        control,
        2 * 1024**2,
    )
    scope = request.scope
    if (
        request.schema_version != original.actor_request_ref.content_schema
        or (scope.owner, scope.task, scope.context_id)
        != (original.scope.owner, original.scope.task, original.scope.context_id)
        or trace.scope != scope
        or request.initial_observation_ref != trace.initial_observation_ref
        or len(request.parameters_refs) != trace.max_generations
    ):
        raise OwnershipConflict(
            "Native Teacher source changed original Actor task/context/limits"
        )
    if (evaluation.identity, evaluation.attempt_id) != (scope.task, scope.attempt_id):
        raise OwnershipConflict("Feedback belongs to another original task/attempt")
    if tuple(c.name for c in evaluation.checks) != original.feedback.check_names:
        raise EvidenceIntegrityError(
            "Feedback policy must cover all original checks exactly; no silent dropping"
        )
    if (
        trace.stop_reason in ("cancelled", "error", "uncertain")
        and evaluation.status != "unknown"
    ):
        raise EvidenceIntegrityError(
            "Incomplete Actor cannot become a scored task failure"
        )
    if (
        request.schema_version == "actor-run-request/2"
        and request.revision_round != max(0, original.candidate_slot - 3)
    ):
        raise OwnershipConflict(
            "Native Teacher changed original candidate revision round"
        )
    stop = canonical(
        trace.stop_evidence_ref, "trace-stop/1", ActorStop, evidence, control
    )
    if (
        stop.request_ref,
        stop.scope,
        stop.reason,
        stop.generations,
        stop.interactions,
        stop.final_observation_ref,
    ) != (
        original.actor_request_ref,
        scope,
        trace.stop_reason,
        trace.generations,
        trace.interactions,
        trace.final_observation_ref,
    ):
        raise EvidenceIntegrityError(
            "Native Teacher stop is not the original Actor request/trace"
        )
    cache: dict[str, ResolvedObservation] = {}

    def observation(ref: EvidenceRef) -> ResolvedObservation:
        key = ref.model_dump_json()
        if key not in cache:
            record = public_records[ref.model_dump_json()]
            resolved = observations.load(ref, op)
            if resolved.record != record or (
                record.task,
                record.context_id,
                record.attempt_id,
            ) != (scope.task, scope.context_id, scope.attempt_id):
                raise EvidenceIntegrityError(
                    "Native Teacher observation changed original record/scope"
                )
            if record.artifacts:
                raise ValueError(
                    "Text Teacher attempt requires explicit artifact support; do not omit artifacts"
                )
            cache[key] = resolved
        return cache[key]

    initial = observation(trace.initial_observation_ref)
    initial.record.check_initial(scope.task, scope.context_id)
    parts = []
    read_indices: dict[str, ObservationIndex] = {}
    visible_bytes = 0
    for index, t in enumerate(trace.turns):
        control.checkpoint()
        gen = t.generation
        if gen.parameters_ref != request.parameters_refs[index] or (
            (gen.schema_version == "actor-generation/2")
            != (request.schema_version == "actor-run-request/2")
        ):
            raise EvidenceIntegrityError(
                "Native Teacher lost original turn parameters/context version"
            )
        before = observation(gen.before_observation_ref)
        sent = canonical(
            gen.input_ref,
            "actor-model-input/1",
            ActorPrompt,
            evidence,
            control,
            8 * 1024**2,
        )
        completion = None
        if gen.response_ref is not None:
            completion = canonical(
                gen.response_ref,
                "actor-model-response/1",
                ActorTextCompletion,
                evidence,
                control,
                1024**2,
            )
            if (
                completion.generation_id,
                completion.request_id,
                completion.input_ref,
                completion.parameters_ref,
                completion.model_input_sha256,
            ) != (
                gen.generation_id,
                gen.request_id,
                gen.input_ref,
                gen.parameters_ref,
                hashlib.sha256(sent.input_bytes()).hexdigest(),
            ):
                raise EvidenceIntegrityError(
                    "Native Teacher completion changed original sent messages"
                )
        parse = None
        if t.decision is not None and t.decision.failure_ref is not None:
            parse = canonical(
                t.decision.failure_ref,
                "actor-parse-failure/1",
                ActorParseFailure,
                evidence,
                control,
                1024**2,
            )
            if (parse.generation_id, parse.response_ref) != (
                gen.generation_id,
                gen.response_ref,
            ):
                raise EvidenceIntegrityError(
                    "Native Teacher parse failure crossed generations"
                )
        raw = None
        after = None
        event = t.interaction
        if event is not None and event.result is not None:
            result = event.result
            raw = canonical(
                result.return_ref,
                "browser-step-return/1",
                BrowserReadout,
                evidence,
                control,
            )
            after = observation(result.observation_ref)
            if (
                (raw.scope, raw.operation, raw.action, raw.observation)
                != (scope, event.operation, event.action, after.record)
                or after.record.sequence != before.record.sequence + 1
                or result.terminal
                != (raw.terminated or raw.truncated or raw.protocol_terminal)
            ):
                raise EvidenceIntegrityError(
                    "Native Teacher browser result differs from actual original return"
                )
        visible_bytes += sum(len(m.content.encode("utf-8")) for m in sent.messages)
        visible_bytes += len((before.text or "").encode("utf-8"))
        if after is not None:
            visible_bytes += len((after.text or "").encode("utf-8"))
        if completion is not None:
            visible_bytes += len(completion.text.encode("utf-8"))
        reading = teacher_observation_read(
            t, before, sent, completion, evidence, control, read_indices
        )
        if reading is not None:
            visible_bytes += len(observation_read_body(reading).encode())
        if visible_bytes > MAX_TEACHER_BYTES:
            raise ValueError(
                "Complete native Teacher attempt exceeds 64MiB before rendering; originals retained"
            )
        parts.append(
            TeacherActorTurn(t, before, sent, completion, parse, raw, after, reading)
        )
    control.checkpoint()
    return TeacherActorMaterial(
        original, request, trace, evaluation, initial, tuple(parts)
    )
