"""Lifecycle dependencies: clocks, cancellation and durable resource history.

register must commit before provider.acquire/task.prepare begins. Registration
is idempotent for identical tokens, never a lease takeover. advance compares
revision and retains original owner. No method performs external cleanup.
"""

from datetime import datetime
from typing import Protocol

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    CancellationRef,
    OperationContext,
    ResourceOwner,
    ResourceRecord,
    ResourceState,
)


class Clock(Protocol):
    """Wall time is for portable deadlines, monotonic time for elapsed limits."""

    def utcnow(self) -> datetime: ...
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class CancellationReader(Protocol):
    """Read explicit cancellation facts without changing operation state."""

    def is_cancelled(self, reference: CancellationRef) -> bool: ...


class OperationControl(Protocol):
    """Bound guard shared across adapter calls for the same operation identity."""

    def checkpoint(self) -> float: ...
    def wait(self, seconds: float) -> None: ...


class OperationControls(Protocol):
    """Bind once; reusing an ID with different context must fail."""

    def bind(self, op: OperationContext) -> OperationControl: ...


class ResourceJournal(Protocol):
    """One immutable owner can inspect and append resource facts, not retry work."""

    def register(
        self, token: AllocationToken, op: OperationContext
    ) -> ResourceRecord: ...
    def begin_acquire(
        self,
        token: AllocationToken,
        intent_ref: EvidenceRef,
        expected_revision: int,
        op: OperationContext,
    ) -> ResourceRecord:
        """Persist acquiring once before effects; replay never grants permission.

        DispatchAlreadyCommitted on the exact original intent, RevisionConflict
        for competing intents. Any commit/cleanup failure grants no launch; read
        back only. Authority/admission and hard I/O supervision are caller duties.
        """
        ...

    def read(self, token: AllocationToken, op: OperationContext) -> ResourceRecord: ...
    def records(
        self, owner: ResourceOwner, op: OperationContext
    ) -> tuple[ResourceRecord, ...]: ...
    def advance(
        self,
        token: AllocationToken,
        state: ResourceState,
        evidence: tuple[EvidenceRef, ...],
        expected_revision: int,
        op: OperationContext,
    ) -> ResourceRecord: ...
