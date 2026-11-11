"""One original Actor call over an acquired worker; no launch, replay or repair.

The trusted root is shared across original callers. A consumed marker survives
caller loss and even known completion; it never becomes a new send permit.
Actual exchange/response facts are persisted under bounded independent cleanup.
Unknown outcomes retain original inputs, raw exchange and candidate refs. The
outer trace/resource owner decides reconciliation and closure without replay.
"""

import hashlib
from pathlib import Path
from typing import Literal
from lab_generate_skill.domain.local_actor import (
    LocalActorBinding,
    LocalActorCall,
    LocalActorExecution,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt, MAX_ACTOR_INPUT_BYTES
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.actor_generation import ActorGeneration
from lab_generate_skill.domain.trace_events import GenerationIntent
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.actor_context import ActorGenerationInputReads
from lab_generate_skill.ports.lifecycle import (
    OperationControl,
    OperationControls,
    Clock,
)
from lab_generate_skill.ports.actor_generation_control import (
    GenerationPreparationControlFactory,
)
from lab_generate_skill.domain.actor_execution_window import ActorDispatchTiming
from lab_generate_skill.ports.local_actor import LocalActorAuthority
from .actor_worker_client import SupervisedActorEngine
from .actor_worker_exchange import ActorWorkerExchange
from .actor_worker_protocol import decode_command, validate_worker_output
from .actor_call_gate import consume_call
from .local_actor_evidence import ActorEvidence


class LocalActorUnconfirmed(RuntimeError):
    def __init__(
        self,
        call: LocalActorCall,
        phase: str,
        primary: BaseException,
        exchange: ActorWorkerExchange | None,
        retained: tuple[EvidenceRef, ...],
        dispatch_timing: ActorDispatchTiming | None = None,
    ) -> None:
        self.call, self.phase, self.primary = call, phase, primary
        self.exchange, self.retained = exchange, retained
        self.dispatch_timing = dispatch_timing
        super().__init__(
            "Actor call unconfirmed in "
            + phase
            + "; preserve original facts and do not resend"
        )


class RecordedLocalActorModel:
    def __init__(
        self,
        root: Path,
        binding: LocalActorBinding,
        engine: SupervisedActorEngine,
        evidence: EvidenceStore,
        controls: OperationControls,
        authority: LocalActorAuthority,
        *,
        inputs: ActorGenerationInputReads | None = None,
        clock: Clock | None = None,
        prepare_control: GenerationPreparationControlFactory | None = None,
    ) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("Actor call root must be a trusted absolute Path")
        self._root, self._binding = root, LocalActorBinding.model_validate(binding)
        self._engine, self._evidence = engine, ActorEvidence(evidence)
        self._controls, self._authority = controls, authority
        self._inputs_read = inputs
        self._clock = clock
        self._prepare_control = prepare_control

    def _preparation_control(
        self, intent: GenerationIntent, control: OperationControl
    ) -> OperationControl:
        if self._prepare_control is not None:
            return self._prepare_control(
                intent.operation, intent.execution_window, control
            )
        if intent.execution_window is not None:
            raise ValueError("Actual generation windows require a preparation guard")
        return control

    def _inputs(
        self,
        intent: GenerationIntent,
        phase: Literal["preflight", "dispatch"],
        control: OperationControl,
    ) -> tuple[LocalActorCall, ActorPrompt, LocalActorParameters]:
        call = LocalActorCall(binding=self._binding, intent=intent)
        control.checkpoint()
        if self._engine.session_id != self._binding.resource.expected_resource_id:
            raise OwnershipConflict("Actor client route differs from original resource")
        # Bind the immutable original deadline as well as honoring the caller's
        # supplied guard. This prevents a changed operation ID/context fallback.
        self._controls.bind(call.intent.operation).checkpoint()
        evidence = (
            self._evidence
            if self._inputs_read is None
            else ActorEvidence(
                self._evidence.store,
                inputs=self._inputs_read.generation_inputs(intent, control),
            )
        )
        prompt = evidence.read(
            intent.input_ref,
            "actor-model-input/1",
            ActorPrompt,
            MAX_ACTOR_INPUT_BYTES,
            control,
        )
        parameters = evidence.read(
            intent.parameters_ref,
            "model-parameters/1",
            LocalActorParameters,
            16384,
            control,
        )
        guard = self._engine.owner_guard
        if guard is None:
            raise OwnershipConflict(
                "Actor worker must already have its original acquired identity"
            )
        self._authority.verify(call, prompt, parameters, guard, phase, control)
        control.checkpoint()
        return call, prompt, parameters

    def validate(self, intent: GenerationIntent, *, control: OperationControl) -> None:
        control = self._preparation_control(intent, control)
        if intent.execution_window is not None and self._clock is None:
            raise ValueError("Actual generation windows require the original clock")
        _, prompt, parameters = self._inputs(intent, "preflight", control)
        self._engine.validate(prompt, parameters, control)

    def generate(
        self, intent: GenerationIntent, *, control: OperationControl
    ) -> ActorGeneration:
        control = self._preparation_control(intent, control)
        if intent.execution_window is not None and self._clock is None:
            raise ValueError("Actual generation windows require the original clock")
        call, prompt, parameters = self._inputs(intent, "dispatch", control)
        retention_seconds = (
            call.binding.cleanup_seconds
            if intent.execution_window is None
            else intent.execution_window.budgets.return_seconds(
                call.binding.cleanup_seconds
            )
        )
        cleanup = intent.operation.cleanup(
            "actor-result-" + call.key,
            now=intent.operation.deadline,
            seconds=retention_seconds,
        )
        result_control = (
            self._controls.bind(cleanup) if intent.execution_window is None else None
        )
        dispatch_timing: ActorDispatchTiming | None = None
        phase = "consume_intent"
        exchange: ActorWorkerExchange | None = None
        retained: list[EvidenceRef] = []
        try:
            consume_call(self._root, call, control)
            phase = "before_send"
            if intent.execution_window is None:
                self._inputs(intent, "dispatch", control)
                phase = "worker_exchange"
                exchange = self._engine.generate_exchange(prompt, parameters, control)
            else:

                def dispatch() -> OperationControl:
                    nonlocal dispatch_timing, phase
                    if dispatch_timing is not None:
                        raise OwnershipConflict(
                            "Actual Actor window may activate only once"
                        )
                    # The worker lock and configuration are already established.
                    # Keep the final dynamic admission inside preparation time.
                    current = self._inputs(intent, "dispatch", control)
                    if current != (call, prompt, parameters):
                        raise OwnershipConflict("Final Actor inputs changed")
                    control.checkpoint()
                    assert (
                        self._clock is not None and intent.execution_window is not None
                    )
                    started = self._clock.utcnow()
                    operation = intent.execution_window.dispatch_operation(
                        intent.operation, started
                    )
                    dispatch_timing = ActorDispatchTiming(
                        started_at=started, operation=operation
                    )
                    phase = "worker_exchange"
                    actual = self._controls.bind(operation)
                    actual.checkpoint()
                    return actual

                exchange = self._engine.generate_exchange(
                    prompt, parameters, control, dispatch=dispatch
                )
                assert self._clock is not None and dispatch_timing is not None
                cleanup = intent.operation.cleanup(
                    "actor-result-" + call.key,
                    now=min(self._clock.utcnow(), intent.operation.deadline),
                    seconds=retention_seconds,
                )
                result_control = self._controls.bind(cleanup)
            assert result_control is not None
            phase = "verify_exchange"
            command = decode_command(exchange.command)
            reply = exchange.decoded_reply
            if (
                command.operation != "generate"
                or command.session_id != self._binding.resource.expected_resource_id
                or command.request != prompt
                or command.parameters != parameters
                or (command.prepared_generation is not None)
                != (intent.execution_window is not None)
                or reply.output is None
            ):
                raise OwnershipConflict(
                    "Actor exchange differs from exact original invocation"
                )
            output = validate_worker_output(reply.output, parameters)
            guard = self._engine.owner_guard
            assert guard is not None
            phase = "retain_actual_return"
            command_ref = self._evidence.put(
                exchange.command, "actor-worker-command/1", retained, result_control
            )
            reply_ref = self._evidence.put(
                exchange.reply, "actor-worker-reply/1", retained, result_control
            )
            completion = ActorTextCompletion(
                generation_id=intent.generation_id,
                request_id=intent.request_id,
                input_ref=intent.input_ref,
                model_input_sha256=hashlib.sha256(prompt.input_bytes()).hexdigest(),
                parameters_ref=intent.parameters_ref,
                text=output.text,
                finish_reason=output.finish_reason,
            )
            response_ref = self._evidence.put(
                completion.model_dump_json().encode(),
                "actor-model-response/1",
                retained,
                result_control,
            )
            execution = LocalActorExecution(
                call=call,
                guard=guard,
                command_ref=command_ref,
                reply_ref=reply_ref,
                response_ref=response_ref,
                output=output,
                dispatch_timing=dispatch_timing,
            )
            self._authority.verify_return(execution, result_control)
            self._evidence.put(
                execution.model_dump_json().encode(),
                "local-actor-execution/1",
                retained,
                result_control,
            )
            return ActorGeneration(
                schema_version=(
                    "actor-generation/2"
                    if intent.schema_version == "actor-generation-intent/2"
                    else "actor-generation/1"
                ),
                **intent.model_dump(exclude={"schema_version"}),
                status="completed",
                response_ref=response_ref,
            )
        except BaseException as error:
            raise LocalActorUnconfirmed(
                call, phase, error, exchange, tuple(retained), dispatch_timing
            ) from error
