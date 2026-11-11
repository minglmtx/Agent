"""One causally ordered run stream, including all of its attempt events.

Input: frozen RunBinding and discriminated run/attempt entries. Output: a
validated snapshot with one global revision and deterministic record views.
Individual histories retain their local predecessor/revision contracts. The
global stream prevents cross-attempt ID collisions and work after run closure.
This module is pure; it neither reads evidence nor commits a transaction.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .execution import (
    AttemptBinding,
    AttemptEvent,
    AttemptRecord,
    RunBinding,
    RunEvent,
    RunRecord,
    append_attempt_event,
    append_run_event,
)
from .validation import Contract
from .journal_capacity import JournalCapacity
from .errors import JournalCapacityExceeded


class RunEntry(Contract):
    schema_version: Literal["run-journal-run-entry/1"] = "run-journal-run-entry/1"
    kind: Literal["run"] = "run"
    event: RunEvent


class AttemptEntry(Contract):
    schema_version: Literal["run-journal-attempt-entry/1"] = (
        "run-journal-attempt-entry/1"
    )
    kind: Literal["attempt"] = "attempt"
    binding: AttemptBinding
    event: AttemptEvent


JournalEntry = Annotated[RunEntry | AttemptEntry, Field(discriminator="kind")]


class RunSnapshot(Contract):
    """Atomic snapshot of one run's total event order, not an execution permit.

    Normal run closing waits for sealed attempt diagnostics. A stopped run may
    start closing first; only attempt cleanup is allowed afterwards. Run seal
    waits for every attempt history to seal, regardless of cleanup success.
    """

    schema_version: Literal["run-journal-snapshot/2"] = "run-journal-snapshot/2"
    binding: RunBinding
    capacity: JournalCapacity
    entries: tuple[JournalEntry, ...] = Field(min_length=1, max_length=10000)

    def project(self) -> tuple[RunRecord, tuple[AttemptRecord, ...]]:
        """Rebuild views from commit order; reject invalid interleavings."""
        first = self.entries[0]
        if not isinstance(first, RunEntry) or first.event.stage != "planned":
            raise ValueError("Run journal starts with its planned run event")
        run = RunRecord(binding=self.binding, events=(first.event,))
        attempts: dict[str, AttemptRecord] = {}
        operations = {first.event.operation.operation_id}
        sizes = [len(entry.model_dump_json().encode()) for entry in self.entries]
        if any(size > self.capacity.max_entry_bytes for size in sizes):
            raise JournalCapacityExceeded("Entry exceeds frozen encoded byte ceiling")
        envelope = len(self.model_dump_json().encode()) - sum(sizes) - (len(sizes) - 1)
        self.capacity.preflight(envelope)
        used_bytes = envelope + sizes[0]
        self._check_capacity(run, tuple(attempts.values()), 1, used_bytes)
        for index, entry in enumerate(self.entries[1:], start=1):
            op_id = entry.event.operation.operation_id
            if op_id in operations:
                raise ValueError("Operation ID must be unique across the entire run")
            operations.add(op_id)
            if run.stage == "sealed":
                raise ValueError("Sealed run journal cannot gain events")
            if isinstance(entry, RunEntry):
                unfinished = any(
                    record.stage != "sealed" for record in attempts.values()
                )
                if unfinished and (
                    entry.event.stage == "sealed"
                    or (
                        entry.event.stage == "closing"
                        and entry.event.stop_reason is None
                    )
                ):
                    raise ValueError("Run closure requires sealed attempt diagnostics")
                run = append_run_event(run, entry.event, run.revision)
            else:
                if entry.binding.run != self.binding:
                    raise ValueError("Attempt binding must retain the original run")
                attempt_id = entry.binding.attempt_id
                prior = attempts.get(attempt_id)
                if prior is None:
                    if run.stage != "running":
                        raise ValueError("New attempts require a running run")
                    attempts[attempt_id] = AttemptRecord(
                        binding=entry.binding, events=(entry.event,)
                    )
                else:
                    if prior.binding != entry.binding:
                        raise ValueError(
                            "Attempt ID already binds another task or claim"
                        )
                    if run.stage != "running" and entry.event.stage not in (
                        "closing",
                        "restoring",
                        "sealed",
                    ):
                        raise ValueError("Stopped run permits only attempt cleanup")
                    attempts[attempt_id] = append_attempt_event(
                        prior, entry.event, prior.revision
                    )
            used_bytes += sizes[index] + 1
            self._check_capacity(run, tuple(attempts.values()), index + 1, used_bytes)
        return run, tuple(attempts.values())

    def _check_capacity(
        self,
        run: RunRecord,
        attempts: tuple[AttemptRecord, ...],
        entries: int,
        encoded_bytes: int,
    ) -> None:
        pending = {"sealed": 0, "closing": 1, "submitting": 3}.get(run.stage, 2)
        pending += sum(
            {"sealed": 0, "restoring": 1, "closing": 2}.get(record.stage, 3)
            for record in attempts
        )
        self.capacity.check(
            entries=entries,
            encoded_bytes=encoded_bytes,
            pending_closures=pending,
            attempts=len(attempts),
        )

    @model_validator(mode="after")
    def validate_interleaving(self) -> Self:
        self.project()
        return self

    @property
    def revision(self) -> int:
        """Global run revision, distinct from any local record revision."""
        return len(self.entries) - 1
