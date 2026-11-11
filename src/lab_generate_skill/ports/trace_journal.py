"""Durable attempt trace gates, separate from model/browser dispatch adapters.

New intent is acknowledged once after transaction cleanup; replay raises
DispatchAlreadyCommitted. Read and observed-fact replay never permit execution.
Live claim/writer/resource exclusivity and paid request permits remain required.
"""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.trace_events import (
    TraceProgressEvent,
    InteractionObserved,
    ReadObserved,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_plan import TracePlan
from .traces import TraceAuthority
from .actor_context import ActorGenerationInputReads
from .evidence import EvidenceReader
from .lifecycle import OperationControl


@runtime_checkable
class TraceInteractionInputReads(Protocol):
    def interaction_inputs(
        self,
        event: InteractionObserved,
        op: OperationContext,
        control: OperationControl,
    ) -> EvidenceReader | None:
        """Original publisher's complete return bodies, with fresh authority."""
        ...


class TraceJournal(Protocol):
    def create(self, plan: TracePlan, op: OperationContext) -> TraceSnapshot: ...
    def read(self, op: OperationContext) -> TraceSnapshot: ...
    def append(
        self, event: TraceProgressEvent, expected_revision: int, op: OperationContext
    ) -> TraceSnapshot: ...


class TraceJournalAuthority(TraceAuthority, Protocol):
    """Verify real plan/limits, original writer, execution and record provenance.

    Callbacks are local validation only, under the journal lock. They may not run
    models, mutate a browser, silently retry or grant takeover from an expired lease.
    """

    def verify_plan(self, plan: TracePlan, op: OperationContext) -> None: ...
    def verify_event(
        self, snapshot: TraceSnapshot, event: TraceProgressEvent, op: OperationContext
    ) -> None: ...


@runtime_checkable
class TraceGenerationInputHandoff(Protocol):
    def with_generation_inputs(self, inputs: ActorGenerationInputReads) -> TraceJournal:
        """Same original journal/authority; scoped immutable result dependencies."""
        ...


@runtime_checkable
class TraceReadingInputs(Protocol):
    def reading_inputs(
        self, event: ReadObserved, control: OperationControl
    ) -> EvidenceReader:
        """Same original reading's verified returned bodies, not all-history content."""
        ...

    def verify_reading(
        self,
        before: TraceSnapshot,
        event: ReadObserved,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        """Original source ranges/native count frames and registered-return lineage."""
        ...


@runtime_checkable
class TraceReadingInputHandoff(Protocol):
    def with_reading_inputs(self, inputs: TraceReadingInputs) -> TraceJournal:
        """Bind the original current reader to this same journal/authority."""
        ...
