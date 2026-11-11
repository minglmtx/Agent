"""Controlled preparation and read-only input verification in the original loop."""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.actor_context import ActorPreparedInput
from lab_generate_skill.domain.actor_generation import ActorGeneration
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_prompt import ActorPrompt, ActorPublicTurn
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.trace import TraceTurn
from lab_generate_skill.domain.observation_read import (
    ObservationReadPayload,
    ObservationReadRequest,
)
from lab_generate_skill.domain.trace_events import GenerationIntent
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl
from .evidence import EvidenceReader, EvidenceStore


class ActorGenerationInputReads(Protocol):
    def generation_inputs(
        self, intent: GenerationIntent, control: OperationControl
    ) -> EvidenceReader:
        """Exact immutable inputs of one bound run; never dispatch permission."""
        ...


@runtime_checkable
class ActorDecisionInputReads(Protocol):
    def decision_inputs(
        self, generation: ActorGeneration, control: OperationControl
    ) -> EvidenceStore:
        """Confirmed current generation's bounded bodies; no dispatch permission."""
        ...


class ActorInputPreparation(Protocol):
    def prepare(
        self,
        request: ActorRunRequest,
        before: TraceSnapshot,
        operation: OperationContext,
        request_id: str,
        *,
        control: OperationControl,
    ) -> ActorPreparedInput: ...


class ActorContextInputReview(Protocol):
    def verify(
        self,
        request: ActorRunRequest,
        before: TraceSnapshot,
        intent: GenerationIntent,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> ActorPrompt: ...


@runtime_checkable
class ActorObservationProposalReview(Protocol):
    def verify_proposal(
        self,
        prompt: ActorPrompt,
        reading: ObservationReadRequest,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> None:
        """Check the just-verified recorded input; no live reader or redispatch."""
        ...


@runtime_checkable
class ActorRecordedProposalChecks(Protocol):
    def check_recorded_proposal(
        self,
        public: ActorPublicTurn,
        prompt: ActorPrompt,
        reading: ObservationReadRequest,
        *,
        control: OperationControl,
    ) -> None: ...


@runtime_checkable
class ActorObservationReadReview(Protocol):
    def verify_reading(
        self,
        request: ActorRunRequest,
        turn: TraceTurn,
        prompt: ActorPrompt,
        completion: ActorTextCompletion,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> ObservationReadPayload:
        """Original read result plus actual resident count frames; no recount or dispatch."""
        ...


@runtime_checkable
class ActorContextInputLifetime(Protocol):
    def clear_inputs(self) -> None:
        """Discard only in-process immutable inputs; no I/O or permission change."""
        ...


@runtime_checkable
class ActorContextPreparationInputHandoff(Protocol):
    def preparation_inputs(
        self,
        request: ActorRunRequest,
        operation: OperationContext,
        request_id: str,
        original: EvidenceStore,
        control: OperationControl,
    ) -> EvidenceStore: ...

    def prepared_inputs(
        self, prepared: ActorPreparedInput, control: OperationControl
    ) -> None: ...

    def discard_preparation_inputs(self) -> None: ...


class ActorObservationSources(Protocol):
    def prepare_public_source(
        self,
        request: ActorRunRequest,
        before: TraceSnapshot,
        operation: OperationContext,
        public: ActorPublicTurn,
        *,
        control: OperationControl,
        inputs: EvidenceReader | None = None,
    ) -> ActorPublicTurn:
        """Original already-captured public source; no extra observation or model call."""
        ...

    def verify_public_source(
        self,
        request: ActorRunRequest,
        before: TraceSnapshot,
        operation: OperationContext,
        public: ActorPublicTurn,
        recorded: ActorPublicTurn,
        *,
        control: OperationControl,
    ) -> None:
        """Immutable original public source/window lineage; never a live send permit."""
        ...

    def clear_inputs(self) -> None: ...
