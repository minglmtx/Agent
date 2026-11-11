"""Immutable live trace history with prefix capacity and exact result replay."""

from typing import Literal, Self
from pydantic import Field, TypeAdapter, model_validator
from .errors import (
    DispatchAlreadyCommitted,
    JournalCapacityExceeded,
    OwnershipConflict,
    RevisionConflict,
)
from .evidence import EvidenceRef
from .lifecycle import OperationContext
from .trace_events import (
    ActionPlanned,
    GenerationPlanned,
    TraceProgressEvent,
    ReadPlanned,
)
from .trace_plan import TracePlan
from .trace_progress import TraceProjection, check_trace_operation
from .validation import Contract

TRACE_EVENT: TypeAdapter[TraceProgressEvent] = TypeAdapter(TraceProgressEvent)


class TraceSnapshot(Contract):
    schema_version: Literal["trace-journal-snapshot/1"] = "trace-journal-snapshot/1"
    plan: TracePlan
    creation_operation: OperationContext
    events: tuple[TraceProgressEvent, ...] = Field(max_length=50001)

    @property
    def revision(self) -> int:
        return len(self.events)

    def project(self) -> TraceProjection:
        view = TraceProjection(operation_ids={self.creation_operation.operation_id})
        for event in self.events:
            view.advance(self.plan, event)
        return view

    @model_validator(mode="after")
    def validate_prefixes_and_reserves(self) -> Self:
        self._check_history()
        return self

    def _check_history(self) -> None:
        check_trace_operation(self.plan, self.creation_operation, execute=True)
        capacity = self.plan.capacity
        sizes = [len(event.model_dump_json().encode()) for event in self.events]
        shell = (
            len(self.model_dump_json().encode()) - sum(sizes) - max(0, len(sizes) - 1)
        )
        ceiling = min(
            capacity.max_bytes, capacity.max_trace_bytes - capacity.max_event_bytes
        )
        if shell + 5 * (capacity.max_event_bytes + 1) > ceiling:
            raise JournalCapacityExceeded(
                "Trace envelope leaves no first-turn completion space"
            )
        view = TraceProjection(operation_ids={self.creation_operation.operation_id})
        used = shell
        for count, (event, size) in enumerate(zip(self.events, sizes), start=1):
            view.advance(self.plan, event)
            used += size + int(count > 1)
            if (
                size > capacity.max_event_bytes
                or count + view.reserve > capacity.max_events
                or used + view.reserve * (capacity.max_event_bytes + 1) > ceiling
            ):
                raise JournalCapacityExceeded(
                    "Trace history would consume its result/seal reserve"
                )
        if (
            view.sealed is not None
            and len(view.sealed.model_dump_json().encode()) > capacity.max_trace_bytes
        ):
            raise JournalCapacityExceeded("Final trace exceeds frozen export ceiling")


def trace_event_replayed(
    snapshot: TraceSnapshot, event: TraceProgressEvent, expected_revision: int
) -> bool:
    snapshot = TraceSnapshot.model_validate(snapshot)
    event = TRACE_EVENT.validate_python(event, strict=True)
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Expected revision must be a nonnegative integer")
    for old in snapshot.events:
        if old.operation.operation_id == event.operation.operation_id:
            if old != event:
                raise OwnershipConflict(
                    "Original trace operation cannot change payload"
                )
            if isinstance(event, (GenerationPlanned, ActionPlanned, ReadPlanned)):
                raise DispatchAlreadyCommitted(
                    "Trace intent already committed; inspect original outcome, do not dispatch again"
                )
            return True
    if expected_revision != snapshot.revision:
        raise RevisionConflict("Trace revision changed")
    return False


def append_trace_event(
    snapshot: TraceSnapshot, event: TraceProgressEvent, expected_revision: int
) -> TraceSnapshot:
    snapshot = TraceSnapshot.model_validate(snapshot)
    event = TRACE_EVENT.validate_python(event, strict=True)
    if trace_event_replayed(snapshot, event, expected_revision):
        return snapshot
    candidate = snapshot.model_copy(update={"events": (*snapshot.events, event)})
    # Both inputs were strictly validated. Keep classified transition/capacity
    # errors at this operation boundary, then validate the complete new value.
    candidate._check_history()
    return TraceSnapshot.model_validate(candidate)


class TraceJournalCommitUnconfirmed(RuntimeError):
    reason_code = "TRACE_JOURNAL_COMMIT_UNCONFIRMED"

    def __init__(self, event_ref: EvidenceRef) -> None:
        self.event_ref = event_ref
        super().__init__(
            "Original trace fact is saved; reconcile its journal commit without repeating execution"
        )
