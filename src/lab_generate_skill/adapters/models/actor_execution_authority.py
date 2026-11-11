"""Compose original acquired Actor provenance with mandatory business admission."""

from typing import Literal
from lab_generate_skill.domain.local_actor import LocalActorCall, LocalActorExecution
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.local_actor import LocalActorAuthority
from lab_generate_skill.ports.actor_context import ActorGenerationInputReads
from .actor_execution_scope import ActorExecutionScope
from .actor_execution_evidence import verify_execution
from .local_actor_evidence import ActorEvidence


class ResourceLocalActorAuthority:
    def __init__(
        self,
        scope: ActorExecutionScope,
        business: LocalActorAuthority,
        *,
        inputs: ActorGenerationInputReads | None = None,
    ) -> None:
        self.scope, self.business = scope, business
        if inputs is not None and not callable(
            getattr(inputs, "generation_inputs", None)
        ):
            raise TypeError("Original scoped generation input supplier required")
        self.inputs = inputs

    def verify(
        self,
        call: LocalActorCall,
        prompt: ActorPrompt,
        parameters: LocalActorParameters,
        guard: ProcessOwnerGuard,
        phase: Literal["preflight", "dispatch"],
        control: OperationControl,
    ) -> None:
        call = LocalActorCall.model_validate(call)
        if guard != self.scope.guard:
            raise OwnershipConflict(
                "Actor authority guard differs from original resource"
            )
        self.scope.require_original(
            call.binding, call.intent.operation, control, live=True
        )
        self.business.verify(call, prompt, parameters, guard, phase, control)
        # Business checks may block; confirm original ownership immediately
        # before returning to the one-send gate/worker call.
        self.scope.require_original(
            call.binding, call.intent.operation, control, live=True
        )

    def verify_return(
        self, execution: LocalActorExecution, control: OperationControl
    ) -> None:
        execution = LocalActorExecution.model_validate(execution)
        if execution.guard != self.scope.guard:
            raise OwnershipConflict("Actor return guard differs from original resource")
        call = execution.call
        cleanup = call.intent.operation.cleanup(
            "actor-result-" + call.key,
            now=call.intent.operation.deadline,
            seconds=(
                call.binding.cleanup_seconds
                if call.intent.execution_window is None
                else call.intent.execution_window.budgets.return_seconds(
                    call.binding.cleanup_seconds
                )
            ),
        )
        self.scope.require_original(call.binding, cleanup, control, live=False)
        evidence = self.scope.evidence
        if self.inputs is not None:
            evidence = ActorEvidence(
                evidence.store,
                inputs=self.inputs.generation_inputs(call.intent, control),
            )
        verify_execution(self.scope.evidence, execution, control, inputs=evidence)
        self.business.verify_return(execution, control)
