"""Pure evidence-session history/CAS transitions and reserved closure capacity.

No release from lease age or outcome alone. Exact fact replay is readback, never
dispatch permission. Capacity is frozen and reserves remaining resolution slots
for the active exchange before accepting any new intent.
"""

from typing import Literal, Self
from pydantic import model_validator
from .lifecycle import OperationContext
from .validation import Contract
from .errors import (
    DispatchAlreadyCommitted,
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
    JournalCapacityExceeded,
    EvidenceNotFound,
)
from .evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceSessionCapacity,
    EvidenceSessionEntry,
    EvidenceOperationIntent,
    EvidenceOperationOutcome,
    EvidenceSessionResolution,
    MAX_OUTCOME_BYTES,
    MAX_RESOLUTION_BYTES,
    EvidenceWorkerInstance,
    resolution_allows_reuse,
)


class EvidenceSessionSnapshot(Contract):
    schema_version: Literal["evidence-session-snapshot/3"] = (
        "evidence-session-snapshot/3"
    )
    binding: EvidenceSessionBinding
    capacity: EvidenceSessionCapacity
    entries: tuple[EvidenceSessionEntry, ...] = ()

    @property
    def revision(self) -> int:
        return sum(
            1 + int(e.outcome is not None) + len(e.resolutions) for e in self.entries
        )

    @model_validator(mode="after")
    def history(self) -> Self:
        exchanges: set[str] = set()
        operations: dict[str, OperationContext] = {}
        outcomes: set[str] = set()
        resolutions: set[str] = set()
        workers: set[EvidenceWorkerInstance] = set()
        for index, entry in enumerate(self.entries):
            op = entry.intent.operation
            if (op.run_id, op.owner_id) != (
                self.binding.owner.run_id,
                self.binding.owner.owner_id,
            ):
                raise ValueError("Evidence operation belongs to another session owner")
            if entry.intent.exchange_id in exchanges:
                raise ValueError("Evidence exchange identities are unique")
            prior_operation = operations.get(op.operation_id)
            if prior_operation is not None and prior_operation != op:
                raise ValueError("Evidence operation ID cannot change bound context")
            exchanges.add(entry.intent.exchange_id)
            operations[op.operation_id] = op
            if entry.intent.worker in workers:
                raise ValueError("One-exchange worker incarnation cannot be reused")
            workers.add(entry.intent.worker)
            if entry.outcome is not None:
                if entry.outcome.outcome_id in outcomes:
                    raise ValueError("Outcome identity reused")
                outcomes.add(entry.outcome.outcome_id)
            for resolution in entry.resolutions:
                if (
                    resolution.resolution_id in resolutions
                    or resolution.operation.operation_id in operations
                ):
                    raise ValueError("Resolution identity or operation reused")
                resolutions.add(resolution.resolution_id)
                operations[resolution.operation.operation_id] = resolution.operation
            if index != len(self.entries) - 1 and not entry.reusable:
                raise ValueError("Unresolved evidence exchange blocks later intents")
        check_session_capacity(self)
        return self


def check_session_capacity(snapshot: EvidenceSessionSnapshot) -> None:
    capacity = snapshot.capacity
    if len(snapshot.entries) > capacity.max_exchanges:
        raise JournalCapacityExceeded("Evidence session exchange limit reached")
    for entry in snapshot.entries:
        if len(entry.resolutions) > capacity.max_resolutions_per_exchange:
            raise JournalCapacityExceeded("Evidence session resolution limit reached")
    # Exact serialized lengths, scanned once. A short terminal snapshot cannot
    # conceal an earlier intent that lacked the promised closure capacity.
    final_sizes = [len(entry.model_dump_json().encode()) for entry in snapshot.entries]
    committed = (
        len(snapshot.model_dump_json().encode())
        - sum(final_sizes)
        - max(0, len(final_sizes) - 1)
    )

    def require_size(size: int, reserve: int = 0) -> None:
        if size + reserve > capacity.max_bytes:
            raise JournalCapacityExceeded(
                "Evidence session must preserve closure byte reserve at every prefix"
            )

    require_size(committed)
    for index, entry in enumerate(snapshot.entries):
        current = (
            committed
            + int(index > 0)
            + len(EvidenceSessionEntry(intent=entry.intent).model_dump_json().encode())
        )
        reserve = capacity.max_resolutions_per_exchange * (MAX_RESOLUTION_BYTES + 1)
        require_size(current, reserve + MAX_OUTCOME_BYTES)
        if entry.outcome is not None:
            current += (
                len(entry.outcome.model_dump_json().encode()) - 4
            )  # replaces null
            require_size(current, reserve)
        for ordinal, result in enumerate(entry.resolutions):
            current += len(result.model_dump_json().encode()) + int(ordinal > 0)
            remaining = capacity.max_resolutions_per_exchange - ordinal - 1
            reserve = (
                0
                if resolution_allows_reuse(entry.outcome, result)
                else remaining * (MAX_RESOLUTION_BYTES + 1)
            )
            require_size(current, reserve)
        committed = current


def _expected(expected: int) -> None:
    if type(expected) is not int or expected < 0:
        raise RevisionConflict(
            "Evidence session revision must be a nonnegative integer"
        )


def _revision(snapshot: EvidenceSessionSnapshot, expected: int) -> None:
    _expected(expected)
    if expected != snapshot.revision:
        raise RevisionConflict("Evidence session revision changed")


def begin_evidence_exchange(
    snapshot: EvidenceSessionSnapshot,
    intent: EvidenceOperationIntent,
    expected_revision: int,
) -> EvidenceSessionSnapshot:
    _expected(expected_revision)
    snapshot = EvidenceSessionSnapshot.model_validate(snapshot)
    intent = EvidenceOperationIntent.model_validate(intent)
    for entry in snapshot.entries:
        if entry.intent.exchange_id == intent.exchange_id:
            if entry.intent != intent:
                raise OwnershipConflict("Exchange ID is bound to another command")
            raise DispatchAlreadyCommitted(
                "Original evidence intent may already have executed"
            )
    _revision(snapshot, expected_revision)
    if snapshot.entries and not snapshot.entries[-1].reusable:
        raise InvalidTransition("Original evidence exchange must be reconciled first")
    return EvidenceSessionSnapshot(
        binding=snapshot.binding,
        capacity=snapshot.capacity,
        entries=(*snapshot.entries, EvidenceSessionEntry(intent=intent)),
    )


def record_evidence_outcome(
    snapshot: EvidenceSessionSnapshot,
    outcome: EvidenceOperationOutcome,
    expected_revision: int,
) -> EvidenceSessionSnapshot:
    _expected(expected_revision)
    snapshot = EvidenceSessionSnapshot.model_validate(snapshot)
    outcome = EvidenceOperationOutcome.model_validate(outcome)
    for index, entry in enumerate(snapshot.entries):
        if entry.intent.exchange_id == outcome.exchange_id:
            if entry.outcome is not None:
                if entry.outcome != outcome:
                    raise OwnershipConflict(
                        "Original evidence outcome cannot be rewritten"
                    )
                return snapshot
            _revision(snapshot, expected_revision)
            if index != len(snapshot.entries) - 1 or entry.resolutions:
                raise InvalidTransition(
                    "Reconciliation cannot invent a late worker outcome"
                )
            changed = EvidenceSessionEntry(intent=entry.intent, outcome=outcome)
            return EvidenceSessionSnapshot(
                binding=snapshot.binding,
                capacity=snapshot.capacity,
                entries=(*snapshot.entries[:-1], changed),
            )
    raise EvidenceNotFound("Original evidence intent is missing")


def resolve_evidence_exchange(
    snapshot: EvidenceSessionSnapshot,
    resolution: EvidenceSessionResolution,
    expected_revision: int,
) -> EvidenceSessionSnapshot:
    _expected(expected_revision)
    snapshot = EvidenceSessionSnapshot.model_validate(snapshot)
    resolution = EvidenceSessionResolution.model_validate(resolution)
    for index, entry in enumerate(snapshot.entries):
        if entry.intent.exchange_id == resolution.exchange_id:
            for prior in entry.resolutions:
                if prior.resolution_id == resolution.resolution_id:
                    if prior != resolution:
                        raise OwnershipConflict("Resolution ID is bound to other facts")
                    return snapshot
            _revision(snapshot, expected_revision)
            if index != len(snapshot.entries) - 1 or entry.reusable:
                raise InvalidTransition("Resolved exchange cannot be altered")
            changed = EvidenceSessionEntry(
                intent=entry.intent,
                outcome=entry.outcome,
                resolutions=(*entry.resolutions, resolution),
            )
            return EvidenceSessionSnapshot(
                binding=snapshot.binding,
                capacity=snapshot.capacity,
                entries=(*snapshot.entries[:-1], changed),
            )
    raise EvidenceNotFound("Original evidence intent is missing")
