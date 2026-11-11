"""One atomic JSON snapshot and stable lock inode per run, including attempts.

Inputs: pre-existing trusted journal directory, frozen binding, operation guards
and verified EvidenceReader. Output: append-only RunSnapshot. Evidence bytes are
checked before a new commit; semantic truth belongs to independent review.
Lock/read/validate/write/rename/fsync form one transaction. No scheduler, Actor,
claim mutation, evidence deletion or lease takeover is performed here.
"""

import fcntl
import hashlib
import os
import stat
import uuid
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    RevisionConflict,
    JournalCapacityExceeded,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution import RunBinding, RunEvent
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.journal_capacity import JournalCapacity
from lab_generate_skill.domain.run_journal import (
    AttemptEntry,
    JournalEntry,
    RunEntry,
    RunSnapshot,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls


class FileRunJournal:
    """Bounded snapshots; synchronous I/O still requires future hard supervision."""

    _MAX_BYTES = 8 * 1024 * 1024

    def __init__(
        self,
        root: Path,
        binding: RunBinding,
        operations: OperationControls,
        evidence: EvidenceReader,
        *,
        capacity: JournalCapacity,
    ) -> None:
        self._root = root
        self._binding = binding
        self._operations = operations
        self._evidence = evidence
        self._capacity = JournalCapacity.model_validate(capacity)
        self._name = (
            hashlib.sha256(binding.owner.run_id.encode()).hexdigest() + ".run.json"
        )

    def _guard(self, op: OperationContext) -> OperationControl:
        if (
            op.run_id != self._binding.owner.run_id
            or op.owner_id != self._binding.owner.owner_id
        ):
            raise OwnershipConflict(
                "Journal operation must retain original run and owner"
            )
        guard = self._operations.bind(op)
        guard.checkpoint()
        return guard

    def _load(self, directory: int) -> RunSnapshot | None:
        try:
            fd = os.open(
                self._name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory,
            )
        except FileNotFoundError:
            return None
        except OSError as error:
            raise EvidenceIntegrityError("Unsafe run snapshot") from error
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise EvidenceIntegrityError("Run snapshot must be a regular file")
            raw = stream.read(self._MAX_BYTES + 1)
        if len(raw) > self._MAX_BYTES:
            raise EvidenceIntegrityError("Run snapshot exceeds size limit")
        try:
            snapshot = RunSnapshot.model_validate_json(raw)
        except (ValidationError, OwnershipConflict, RevisionConflict) as error:
            raise EvidenceIntegrityError("Invalid run journal history") from error
        if snapshot.binding != self._binding:
            raise OwnershipConflict(
                "Run ID already binds another owner, plan or release"
            )
        if snapshot.capacity != self._capacity:
            raise OwnershipConflict("Run capacity must retain the frozen plan limits")
        return snapshot

    def _verify_refs(
        self, refs: tuple[EvidenceRef, ...], guard: OperationControl
    ) -> None:
        for reference in dict.fromkeys(refs):
            guard.checkpoint()
            self._evidence.read(reference, control=guard)
            guard.checkpoint()

    def _verify_entry(
        self, entry: JournalEntry, op: OperationContext, guard: OperationControl
    ) -> None:
        event = entry.event
        if event.operation != op:
            raise OwnershipConflict("New event must use the exact executing operation")
        refs = (*event.inputs, *event.outputs)
        if event.operation.recovery_ref is not None:
            refs += (event.operation.recovery_ref,)
        if event.primary_error is not None:
            refs += event.primary_error.evidence
        for failure in event.cleanup_errors:
            refs += failure.evidence
        if isinstance(entry, AttemptEntry):
            refs += (entry.binding.claim_ref,)
        self._verify_refs(refs, guard)

    def _transaction(
        self,
        op: OperationContext,
        update: Callable[[RunSnapshot | None, OperationControl], RunSnapshot],
    ) -> RunSnapshot:
        guard = self._guard(op)
        directory = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        lock: int | None = None
        temporary = ".pending-run-" + uuid.uuid4().hex
        created_temporary = False
        primary: BaseException | None = None
        try:
            try:
                lock = os.open(
                    self._name + ".lock",
                    os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                    mode=0o600,
                    dir_fd=directory,
                )
            except OSError as error:
                raise EvidenceIntegrityError("Unsafe run journal lock") from error
            if not stat.S_ISREG(os.fstat(lock).st_mode):
                raise EvidenceIntegrityError("Run journal lock must be a regular file")
            while True:
                guard.checkpoint()
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    guard.wait(0.02)
            current = self._load(directory)
            updated = update(current, guard)
            guard.checkpoint()
            if updated != current:
                raw = updated.model_dump_json().encode()
                if len(raw) > self._MAX_BYTES:
                    raise EvidenceIntegrityError("Run snapshot exceeds size limit")
                fd = os.open(
                    temporary,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    mode=0o600,
                    dir_fd=directory,
                )
                created_temporary = True
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                guard.checkpoint()
                os.replace(
                    temporary, self._name, src_dir_fd=directory, dst_dir_fd=directory
                )
                created_temporary = False
                os.fsync(directory)
            return updated
        except BaseException as error:
            primary = error
            raise
        finally:
            failures: list[Exception] = []
            if created_temporary:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
                except OSError as error:
                    failures.append(error)
            for descriptor in (lock, directory):
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError as error:
                        failures.append(error)
            if failures:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Run transaction and cleanup failed", [primary, *failures]
                    ) from None
                raise ExceptionGroup("Run transaction cleanup failed", failures)

    def create(self, initial: RunEvent, op: OperationContext) -> RunSnapshot:
        """Persist frozen run intent; duplicate create cannot reset progressed state."""
        entry = RunEntry(event=initial)

        def update(current: RunSnapshot | None, guard: OperationControl) -> RunSnapshot:
            if current is not None:
                if current.entries[0] != entry:
                    raise OwnershipConflict("Run already has another initial event")
                return current
            candidate = self._snapshot((entry,))
            self._verify_entry(entry, op, guard)
            self._verify_refs(
                (self._binding.plan_ref, self._binding.release_ref), guard
            )
            return candidate

        return self._transaction(op, update)

    def read(self, op: OperationContext) -> RunSnapshot:
        """Read atomically without a lock file, state mutation or external retries."""
        guard = self._guard(op)
        directory = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        primary: BaseException | None = None
        try:
            current = self._load(directory)
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                os.close(directory)
            except OSError as error:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Run read and cleanup failed", [primary, error]
                    ) from None
                raise
        guard.checkpoint()
        if current is None:
            raise EvidenceNotFound("Run journal has not been created")
        return current

    def append(
        self, entry: JournalEntry, expected_revision: int, op: OperationContext
    ) -> RunSnapshot:
        """Compare the global revision under lock; replay never creates new work."""
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Expected revision must be a nonnegative integer")
        if op.attempt_id != entry.event.operation.attempt_id:
            raise OwnershipConflict("Journal command must address the event's attempt")

        def update(current: RunSnapshot | None, guard: OperationControl) -> RunSnapshot:
            if current is None:
                raise EvidenceNotFound("Create run before appending events")
            for committed in current.entries:
                if (
                    committed.event.operation.operation_id
                    == entry.event.operation.operation_id
                ):
                    if committed != entry:
                        raise OwnershipConflict(
                            "Operation ID already binds another run or attempt event"
                        )
                    return current
            if current.revision != expected_revision:
                raise RevisionConflict("Global run journal revision changed")
            candidate = self._snapshot((*current.entries, entry))
            self._verify_entry(entry, op, guard)
            return candidate

        return self._transaction(op, update)

    def _snapshot(self, entries: tuple[JournalEntry, ...]) -> RunSnapshot:
        try:
            return RunSnapshot(
                binding=self._binding, capacity=self._capacity, entries=entries
            )
        except ValidationError as error:
            for detail in error.errors():
                cause = detail.get("ctx", {}).get("error")
                if isinstance(cause, JournalCapacityExceeded):
                    raise cause from error
            raise
