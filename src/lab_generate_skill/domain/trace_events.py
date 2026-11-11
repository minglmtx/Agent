"""Write-ahead trace intents and observed facts; original execution IDs survive.

Journal commands have distinct identities from the model/browser operations.
Observed facts may be reconciled under new scoped cleanup commands; intents may
not. Registering a dispatch twice never produces a second send opportunity.
"""

from typing import Annotated, Literal, Self, Any
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .actor_versions import actor_version_fields, actor_version_output
from .actor_execution_window import ActorGenerationWindow
from .actor_generation import ActorGeneration, ActorDecision
from .browser import observation_reference
from .evidence import EvidenceRef
from .interaction import InteractionEvent
from .lifecycle import OperationContext
from .state_scope import StateFact, private_state_ref
from .validation import Contract, Identifier
from .observation_read_fact import ObservationReadFact


class GenerationIntent(StateFact):
    schema_version: Literal[
        "actor-generation-intent/1", "actor-generation-intent/2"
    ] = "actor-generation-intent/1"
    context_preparation_ref: EvidenceRef | None = None
    generation_id: Identifier
    request_id: Identifier
    before_observation_ref: EvidenceRef
    input_ref: EvidenceRef
    parameters_ref: EvidenceRef

    execution_window: ActorGenerationWindow | None = None

    @model_serializer(mode="wrap")
    def wire_version(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result = actor_version_output(
            self,
            handler,
            self.schema_version == "actor-generation-intent/1",
            ("context_preparation_ref",),
        )

        if self.execution_window is None:
            result.pop("execution_window", None)
        return result

    @model_validator(mode="after")
    def references(self) -> Self:
        actor_version_fields(
            self,
            self.schema_version == "actor-generation-intent/1",
            ("context_preparation_ref",),
        )
        if (self.schema_version == "actor-generation-intent/2") != (
            self.context_preparation_ref is not None
        ):
            raise ValueError(
                "Actor intent v2 requires its original preparation reference"
            )
        if self.context_preparation_ref is not None:
            private_state_ref(self.context_preparation_ref, "context-preparation/2")
        if self.execution_window is not None:
            self.execution_window.require_original(self.operation)
        observation_reference(self.before_observation_ref)
        private_state_ref(self.input_ref, "actor-model-input/1")
        private_state_ref(self.parameters_ref, "model-parameters/1")
        return self

    def matches(self, fact: ActorGeneration) -> bool:
        return all(
            getattr(self, name) == getattr(fact, name)
            for name in type(self).model_fields
            if name != "schema_version"
        )


class TraceEvent(Contract):
    operation: OperationContext


class GenerationPlanned(TraceEvent):
    kind: Literal["generation_planned"] = "generation_planned"
    intent: GenerationIntent


class GenerationObserved(TraceEvent):
    kind: Literal["generation_observed"] = "generation_observed"
    generation: ActorGeneration


class DecisionRejected(TraceEvent):
    kind: Literal["decision_rejected"] = "decision_rejected"
    decision: ActorDecision


class ActionPlanned(TraceEvent):
    kind: Literal["action_planned"] = "action_planned"
    decision: ActorDecision
    execution_operation: OperationContext


class InteractionObserved(TraceEvent):
    kind: Literal["interaction_observed"] = "interaction_observed"
    interaction: InteractionEvent


class ReadPlanned(TraceEvent):
    kind: Literal["read_planned"] = "read_planned"
    decision: ActorDecision
    execution_operation: OperationContext

    @model_validator(mode="after")
    def readonly_decision(self) -> Self:
        if (
            self.decision.outcome != "read"
            or self.decision.read_request is None
            or self.decision.read_policy is None
        ):
            raise ValueError(
                "Read intent requires its original explicitly parsed read decision"
            )
        return self


class ReadObserved(TraceEvent):
    kind: Literal["read_observed"] = "read_observed"
    reading: ObservationReadFact


class TraceSealed(TraceEvent):
    kind: Literal["sealed"] = "sealed"
    stop_reason: Literal[
        "finished",
        "generation_limit",
        "interaction_limit",
        "cancelled",
        "error",
        "uncertain",
    ]
    stop_evidence_ref: EvidenceRef

    @model_validator(mode="after")
    def diagnostic(self) -> Self:
        private_state_ref(self.stop_evidence_ref, "trace-stop/1")
        return self


TraceProgressEvent = Annotated[
    GenerationPlanned
    | GenerationObserved
    | DecisionRejected
    | ActionPlanned
    | InteractionObserved
    | ReadPlanned
    | ReadObserved
    | TraceSealed,
    Field(discriminator="kind"),
]
