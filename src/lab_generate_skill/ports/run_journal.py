"""Durable per-run transactions, with attempts in the same ordered stream.

The implementation is bound to one immutable RunBinding and explicit
JournalCapacity at construction. Snapshots use schema /2; old snapshots are
never silently upgraded with a guessed default. Capacity rejects new work with
JournalCapacityExceeded before commit, preserving bounded closure events and
bytes, including submission_uncertain when the current stage is submitting.
Application owns physical cleanup and recording its outcome; diagnostic seal
alone never grants resource reuse. Large raw errors must be referenced evidence.
create/append return committed snapshots, never permission to repeat effects.
All writers use the same storage and global expected_revision. Identical entry
replay is idempotent even with a stale revision; changed ID content is refused.
An acknowledgement failure may follow a commit: inspect/replay, never assume
the write did not happen. read is side-effect free and cannot take ownership.
"""

from typing import Protocol

from lab_generate_skill.domain.execution import RunEvent
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_journal import JournalEntry, RunSnapshot


class RunJournal(Protocol):
    def create(self, initial: RunEvent, op: OperationContext) -> RunSnapshot: ...
    def read(self, op: OperationContext) -> RunSnapshot: ...
    def append(
        self,
        entry: JournalEntry,
        expected_revision: int,
        op: OperationContext,
    ) -> RunSnapshot: ...
