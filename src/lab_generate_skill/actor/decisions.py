"""Parse the original saved response; no model call or browser capability.

Response/input/parameter integrity errors propagate and are never classified as
an invalid model choice. Only an actual, correctly bound but unparseable model
response produces an invalid decision. Publication failure retains the original
generation and candidate parse-failure reference, without repeating inference.
"""

import hashlib
import logging
from lab_generate_skill.domain.actor_proposal_feedback import ActorProposalError
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.ports.observation_reads import ObservationProposalChecks
from .proposal_correction import corrective_proposal_feedback
from .schema_response import NEW_PROMPTS, parse_schema_proposal
from lab_generate_skill.policies.actor_parse_failure import REJECTION_PREFIX
from lab_generate_skill.domain.actor_generation import ActorGeneration, ActorDecision
from lab_generate_skill.domain.actor_prompt import (
    ActorPrompt,
    MAX_ACTOR_INPUT_BYTES,
    MAX_ACTOR_RESPONSE_BYTES,
)
from lab_generate_skill.domain.actor_response import (
    ActorTextCompletion,
    ActorParseFailure,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.evidence import EvidenceReader, EvidenceStore
from lab_generate_skill.ports.actor_context import ActorDecisionInputReads
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from .response import parse_actor_action
from .observation_read_response import parse_observation_read


class RecordedActorDecisions:
    def __init__(
        self,
        evidence: EvidenceStore,
        controls: OperationControls,
        *,
        proposals: ObservationProposalChecks | None = None,
        inputs: ActorDecisionInputReads | None = None,
    ) -> None:
        self.evidence, self.controls = evidence, controls
        self.proposals = proposals
        if inputs is not None and not isinstance(inputs, ActorDecisionInputReads):
            raise TypeError("Explicit original decision input supplier required")
        self.inputs = inputs
        self._rejected: tuple[ActorGeneration, ActorDecision, EvidenceReader] | None = (
            None
        )

    def _read(
        self,
        reader: EvidenceReader,
        ref: EvidenceRef,
        maximum: int,
        control: OperationControl,
    ) -> bytes:
        if ref.media_type != "application/json" or not 0 < ref.size_bytes <= maximum:
            raise EvidenceIntegrityError("Actor evidence exceeds JSON byte boundary")
        control.checkpoint()
        raw = reader.read(ref, control=control)
        if (
            type(raw) is not bytes
            or len(raw) != ref.size_bytes
            or hashlib.sha256(raw).hexdigest() != ref.sha256
        ):
            raise EvidenceIntegrityError(
                "Actor evidence differs from original reference"
            )
        control.checkpoint()
        return raw

    def decide(
        self, generation: ActorGeneration, task: PublicTask, operation: OperationContext
    ) -> ActorDecision:
        self._rejected = None
        generation = ActorGeneration.model_validate(generation)
        task = PublicTask.model_validate(task)
        operation = OperationContext.model_validate(operation)
        original = generation.operation
        if generation.scope.task != task.identity or (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
        ) != (original.run_id, original.owner_id, original.attempt_id):
            raise OwnershipConflict("Actor parsing changed original task/attempt")
        if operation.operation_id == original.operation_id:
            raise OwnershipConflict("Parsing needs a distinct bounded operation")
        if (
            operation.mode == "cleanup"
            and operation.parent_operation_id != original.operation_id
        ):
            raise OwnershipConflict(
                "Parsing cleanup must retain original generation parent"
            )
        if generation.status != "completed" or generation.response_ref is None:
            raise ValueError("Only an actual completed response can be parsed")
        control = self.controls.bind(operation)
        store = (
            self.evidence
            if self.inputs is None
            else self.inputs.decision_inputs(generation, control)
        )
        response_raw = self._read(
            store, generation.response_ref, MAX_ACTOR_RESPONSE_BYTES, control
        )
        completion = ActorTextCompletion.model_validate_json(response_raw)
        input_raw = self._read(
            store, generation.input_ref, MAX_ACTOR_INPUT_BYTES, control
        )
        prompt = ActorPrompt.model_validate_json(input_raw)
        self._read(store, generation.parameters_ref, MAX_ACTOR_RESPONSE_BYTES, control)
        if (
            completion.model_dump_json().encode() != response_raw
            or prompt.model_dump_json().encode() != input_raw
        ):
            raise EvidenceIntegrityError("Actor input/completion must be canonical")
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
                "Actor completion changed original request/input/parameters"
            )
        view = prompt.observation_view
        if view is not None and (
            view.snapshot.scope != generation.scope
            or view.snapshot.observation_ref != generation.before_observation_ref
        ):
            raise OwnershipConflict(
                "Actual Actor view changed original generation snapshot/scope"
            )
        try:
            new = prompt.prompt_version in NEW_PROMPTS
            if new:
                parsed = parse_schema_proposal(
                    completion.text,
                    completion.finish_reason,
                    task,
                    prompt,
                    action_id="action-"
                    + hashlib.sha256(generation.generation_id.encode()).hexdigest(),
                    request_id="read-"
                    + hashlib.sha256(generation.generation_id.encode()).hexdigest(),
                )
                reading = None if isinstance(parsed, BrowserAction) else parsed
            else:
                reading = parse_observation_read(
                    completion.text,
                    completion.finish_reason,
                    prompt,
                    request_id="read-"
                    + hashlib.sha256(generation.generation_id.encode()).hexdigest(),
                )
            if reading is not None:
                assert view is not None
                if new:
                    if self.proposals is None:
                        raise OwnershipConflict(
                            "New read proposal has no actual retained-index preflight consumer"
                        )
                    self.proposals.check_proposal(
                        reading, view, operation, control=control
                    )
                control.checkpoint()
                return ActorDecision(
                    schema_version="actor-decision/2",
                    generation_id=generation.generation_id,
                    outcome="read",
                    read_request=reading,
                    read_policy=view.policy,
                    displayed_source_spans=view.source_spans,
                    active_read_ref=view.read_result_ref,
                    active_progress_fingerprint=view.progress_fingerprint,
                )
            action = (
                parsed
                if new and isinstance(parsed, BrowserAction)
                else parse_actor_action(
                    completion.text,
                    completion.finish_reason,
                    task,
                    "action-"
                    + hashlib.sha256(generation.generation_id.encode()).hexdigest(),
                )
            )
        except (ValueError, TypeError, SyntaxError, RecursionError) as error:
            if new and not isinstance(error, ActorProposalError):
                raise
            message = REJECTION_PREFIX + str(error)
            if new:
                assert isinstance(error, ActorProposalError)
                message = corrective_proposal_feedback(
                    error, prompt, completion, task
                ).model_dump_json()
                logging.getLogger(__name__).info(
                    "Actor/decision proposal rejected run=%s task=%s generation=%s request=%s operation=%s deadline=%s",
                    operation.run_id,
                    task.identity.task_id,
                    generation.generation_id,
                    generation.request_id,
                    operation.operation_id,
                    operation.deadline,
                    exc_info=True,
                )
            failure = ActorParseFailure(
                generation_id=generation.generation_id,
                response_ref=generation.response_ref,
                error_type=type(error).__name__,
                message=message,
            )
            raw = failure.model_dump_json().encode()
            metadata = EvidenceMetadata(
                media_type="application/json",
                content_schema=failure.schema_version,
                visibility="private",
                producer="actor-decisions-v1",
            )
            candidate = evidence_reference(raw, metadata)
            reference: EvidenceRef | None = None
            try:
                reference = EvidenceRef.model_validate(
                    store.put(raw, metadata, control=control)
                )
                if reference.model_dump(exclude={"uri"}) != candidate.model_dump(
                    exclude={"uri"}
                ):
                    raise EvidenceIntegrityError(
                        "Actor parse failure publication changed original bytes"
                    )
                control.checkpoint()
            except BaseException as storage_error:
                setattr(storage_error, "actor_generation", generation)
                setattr(storage_error, "actor_parse_failure_candidate", candidate)
                setattr(storage_error, "actor_parse_failure_reference", reference)
                raise
            decision = ActorDecision(
                generation_id=generation.generation_id,
                outcome="invalid",
                failure_ref=reference,
            )
            self._rejected = (generation, decision, store)
            return decision
        control.checkpoint()
        return ActorDecision(
            generation_id=generation.generation_id, outcome="action", action=action
        )

    def rejected_inputs(
        self,
        generation: ActorGeneration,
        decision: ActorDecision,
        control: OperationControl,
    ) -> EvidenceReader:
        control.checkpoint()
        if self._rejected is None or self._rejected[:2] != (generation, decision):
            raise OwnershipConflict(
                "Only the just-confirmed rejection has input bodies"
            )
        reader = self._rejected[2]
        if (
            self.inputs is not None
            and self.inputs.decision_inputs(generation, control) is not reader
        ):
            raise OwnershipConflict("Rejection input lifetime changed")
        return reader
