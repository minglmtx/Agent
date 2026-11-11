"""Inclusive timing hooks for synthetic ledger measurement, never production."""

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from unittest.mock import patch
from lab_generate_skill.adapters.ledger.request_ledger import FileRequestLedger
from lab_generate_skill.adapters.storage.atomic_snapshot import (
    AtomicSnapshotFile,
    SnapshotTransaction,
)
from lab_generate_skill.domain.budget_journal import BudgetJournalSnapshot
from lab_generate_skill.ports.lifecycle import OperationControl


@contextmanager
def timings() -> Iterator[dict[str, float]]:
    values: dict[str, float] = {}
    locked, read, write = (
        AtomicSnapshotFile.locked,
        SnapshotTransaction.read,
        SnapshotTransaction.write,
    )
    load, capacity = FileRequestLedger._load, BudgetJournalSnapshot.check_capacity

    def add(name: str, started: float) -> None:
        values[name] = values.get(name, 0.0) + perf_counter() - started

    @contextmanager
    def lock_wrapper(
        self: AtomicSnapshotFile, control: OperationControl
    ) -> Iterator[SnapshotTransaction]:
        start = perf_counter()
        with locked(self, control) as transaction:
            add("lock_acquire_including_open_seconds", start)
            entered = perf_counter()
            try:
                yield transaction
            finally:
                add("lock_held_body_seconds", entered)
                releasing = perf_counter()
        add("lock_cleanup_seconds", releasing)

    def read_wrapper(self: SnapshotTransaction) -> bytes | None:
        start = perf_counter()
        try:
            return read(self)
        finally:
            add("snapshot_read_seconds", start)

    def write_wrapper(self: SnapshotTransaction, raw: bytes) -> None:
        start = perf_counter()
        try:
            write(self, raw)
        finally:
            add("snapshot_write_fsync_seconds", start)

    def load_wrapper(
        self: FileRequestLedger, raw: bytes | None
    ) -> BudgetJournalSnapshot:
        start = perf_counter()
        try:
            return load(self, raw)
        finally:
            add("load_validate_including_capacity_seconds", start)

    def capacity_wrapper(self: BudgetJournalSnapshot) -> None:
        start = perf_counter()
        try:
            capacity(self)
        finally:
            add("capacity_seconds", start)

    with (
        patch.object(AtomicSnapshotFile, "locked", lock_wrapper),
        patch.object(SnapshotTransaction, "read", read_wrapper),
        patch.object(SnapshotTransaction, "write", write_wrapper),
        patch.object(FileRequestLedger, "_load", load_wrapper),
        patch.object(BudgetJournalSnapshot, "check_capacity", capacity_wrapper),
    ):
        yield values
