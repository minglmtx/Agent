"""Rebuild each Actor input from its original trace and frozen attempt request.

The required run authority checks live source/claim/baseline/resource admission;
this class never grants those rights from parsed documents. The resource adapter
separately checks original model provenance. No execution, retry or mutation is
performed here. Historical return verification reads the original trace prefix
with independent cleanup control, without requiring a still-live website.
"""

from typing import Literal
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_prompt import ActorPrompt, MAX_ACTOR_INPUT_BYTES
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.local_actor import LocalActorCall, LocalActorExecution
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.trace_events import GenerationPlanned, GenerationObserved
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.actor import ActorRunAuthority, ActorProjection
from lab_generate_skill.ports.actor_context import (
    ActorContextInputReview,
    ActorGenerationInputReads,
)
from lab_generate_skill.ports.evidence import EvidenceStore, EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.observations import Observations
from lab_generate_skill.ports.trace_journal import TraceJournal
from .actor_loop_inputs import prepare_turn
from .verified_evidence_inputs import verified_input_document


class TraceActorAuthority:
    def __init__(
        self,
        request: ActorRunRequest,
        journal: TraceJournal,
        evidence: EvidenceStore,
        observations: Observations,
        project: ActorProjection,
        authority: ActorRunAuthority,
        controls: OperationControls,
        *,
        context: ActorContextInputReview | None = None,
        inputs: ActorGenerationInputReads | None = None,
    ) -> None:
        self.request = ActorRunRequest.model_validate(request)
        self.journal, self.evidence, self.observations = journal, evidence, observations
        self.project, self.authority, self.controls = project, authority, controls
        if (self.request.schema_version == "actor-run-request/2") != (
            context is not None
        ):
            raise ValueError(
                "Actor authority requires matching explicit context verifier/version"
            )
        self.context = context
        self.inputs = inputs

    def _input_reader(
        self, call: LocalActorCall, control: OperationControl
    ) -> EvidenceReader:
        return (
            self.evidence
            if self.inputs is None
            else self.inputs.generation_inputs(call.intent, control)
        )

    def _read(
        self,
        call: LocalActorCall,
        control: OperationControl,
        *,
        historical: bool,
    ) -> tuple[TraceSnapshot, OperationContext]:
        call = LocalActorCall.model_validate(call)
        request, intent = self.request, call.intent
        if (
            intent.scope != request.scope
            or call.binding.resource != request.model_allocation
            or call.binding.cleanup_seconds != request.cleanup_seconds
            or intent.operation.deadline > request.operation.deadline
        ):
            raise OwnershipConflict(
                "Actor call changed original attempt/resource/budget"
            )
        selected = request.generation_budgets
        window = intent.execution_window
        if (selected is None) != (window is None) or (
            window is not None and window.budgets != selected
        ):
            raise OwnershipConflict(
                "Actor call changed original selected generation windows"
            )
        if window is not None:
            window.require_original(intent.operation)
            if intent.operation.parent_operation_id != request.operation.operation_id:
                raise OwnershipConflict(
                    "Generation transaction changed original Actor parent"
                )
        op = intent.operation
        if historical:
            op = op.cleanup(
                "actor-return-read-" + call.key,
                now=op.deadline,
                seconds=(
                    call.binding.cleanup_seconds
                    if window is None
                    else window.budgets.return_seconds(call.binding.cleanup_seconds)
                ),
            )
        else:
            self.controls.bind(request.operation).checkpoint()
            op = op.model_copy(update={"operation_id": "actor-input-read-" + call.key})
        self.controls.bind(op).checkpoint()
        control.checkpoint()
        snapshot = TraceSnapshot.model_validate(self.journal.read(op))
        if (
            snapshot.plan.scope != request.scope
            or snapshot.plan.initial_observation_ref != request.initial_observation_ref
            or snapshot.plan.max_generations != len(request.parameters_refs)
        ):
            raise OwnershipConflict("Actor original trace plan differs")
        control.checkpoint()
        return snapshot, op

    def _parameters(
        self, call: LocalActorCall, control: OperationControl
    ) -> LocalActorParameters:
        ref = call.intent.parameters_ref
        if not 0 < ref.size_bytes <= 16384:
            raise EvidenceIntegrityError("Actor parameters exceed read boundary")
        return verified_input_document(
            self._input_reader(call, control), ref, LocalActorParameters, 16384, control
        )

    def _input(
        self,
        call: LocalActorCall,
        before: TraceSnapshot,
        op: OperationContext,
        control: OperationControl,
    ) -> tuple[ActorPrompt, LocalActorParameters]:
        view = before.project()
        index = len(view.turns)
        if (
            view.sealed is not None
            or view.halted
            or view.generation is not None
            or view.action is not None
            or index >= before.plan.max_generations
            or view.interactions >= before.plan.max_interactions
            or call.intent.parameters_ref != self.request.parameters_refs[index]
            or call.intent.before_observation_ref
            != view.current_observation(before.plan)
        ):
            raise OwnershipConflict(
                "Actor generation is not the next original public turn"
            )
        if (self.request.schema_version == "actor-run-request/2") != (
            call.intent.schema_version == "actor-generation-intent/2"
        ):
            raise OwnershipConflict(
                "Actor intent changed original context contract version"
            )
        if self.context is None:
            prompt = prepare_turn(
                self.request,
                before,
                op,
                control,
                self.evidence,
                self.observations,
                self.project,
            )
        else:
            prompt = self.context.verify(
                self.request, before, call.intent, op, control=control
            )
        recorded = verified_input_document(
            self._input_reader(call, control),
            call.intent.input_ref,
            ActorPrompt,
            MAX_ACTOR_INPUT_BYTES,
            control,
        )
        if recorded != prompt:
            raise EvidenceIntegrityError(
                "Actor input differs from original public trace projection"
            )
        return prompt, self._parameters(call, control)

    def verify(
        self,
        call: LocalActorCall,
        prompt: ActorPrompt,
        parameters: LocalActorParameters,
        guard: ProcessOwnerGuard,
        phase: Literal["preflight", "dispatch"],
        control: OperationControl,
    ) -> None:
        snapshot, op = self._read(call, control, historical=False)
        view = snapshot.project()
        if phase == "preflight":
            if view.intent is not None:
                raise OwnershipConflict(
                    "Actor preflight cannot reuse a pending generation"
                )
            before = snapshot
        elif phase == "dispatch":
            if (
                view.intent != call.intent
                or not snapshot.events
                or not isinstance(snapshot.events[-1], GenerationPlanned)
            ):
                raise OwnershipConflict(
                    "Actor dispatch needs the exact original pending intent"
                )
            before = TraceSnapshot.model_validate(
                snapshot.model_copy(update={"events": snapshot.events[:-1]})
            )
        else:
            raise ValueError("Unsupported Actor admission phase")
        expected_prompt, expected_parameters = self._input(call, before, op, control)
        if prompt != expected_prompt or parameters != expected_parameters:
            raise EvidenceIntegrityError(
                "Actor supplied prompt/parameters differ from original projection"
            )
        self.authority.verify(self.request, snapshot, control)
        control.checkpoint()

    def verify_return(
        self, execution: LocalActorExecution, control: OperationControl
    ) -> None:
        execution = LocalActorExecution.model_validate(execution)
        call = execution.call
        snapshot, op = self._read(call, control, historical=True)
        entries = [
            (i, e)
            for i, e in enumerate(snapshot.events)
            if isinstance(e, GenerationPlanned)
            and e.intent.request_id == call.intent.request_id
        ]
        if len(entries) != 1 or entries[0][1].intent != call.intent:
            raise OwnershipConflict(
                "Actor return lacks its exact original trace intent"
            )
        before = TraceSnapshot.model_validate(
            snapshot.model_copy(update={"events": snapshot.events[: entries[0][0]]})
        )
        self._input(call, before, op, control)
        for event in snapshot.events[entries[0][0] + 1 :]:
            if (
                isinstance(event, GenerationObserved)
                and event.generation.request_id == call.intent.request_id
            ):
                if (
                    not call.intent.matches(event.generation)
                    or event.generation.response_ref != execution.response_ref
                ):
                    raise EvidenceIntegrityError(
                        "Actor historical return changed its recorded response"
                    )
        control.checkpoint()
