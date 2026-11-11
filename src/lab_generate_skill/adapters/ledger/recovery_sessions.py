"""Exclusive persistent recovery sessions on a trusted shared filesystem root.

One stable lock per provider/resource incarnation spans inspect/restore/commit.
The record retains the original allocation; another allocation cannot alias the
same target to obtain a separate lock. Providers issue unique, non-reused IDs.
Atomic snapshots retain intent lineage and CAS receipt refs. Prior pending
writers require authority-confirmed quiescence even if flock is available.
Calls are confined to their opening process/thread and bounded by the original
operation guard. Cross-node locks/authority and hard I/O supervision need their
own deployment evidence; this module never infers termination from lock expiry.
"""

import fcntl
import hashlib
import json
import os
import stat
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import ValidationError

from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    ResourceOwner,
)
from lab_generate_skill.domain.recovery import (
    RecoveryIntent,
    RecoveryReceipt,
    WriterTerminationReceipt,
)
from lab_generate_skill.domain.recovery_sessions import (
    RecoverySessionAttempt,
    RecoverySessionRecord,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.recovery import RecoverySession, WriterQuiescence


class FileRecoverySessions:
    _MAX_BYTES = 4 * 1024 * 1024
    _RECEIPT_RESERVE = 4096

    def __init__(
        self,
        root: Path,
        controls: OperationControls,
        evidence: EvidenceStore,
        quiescence: WriterQuiescence,
    ) -> None:
        self._root = root
        self._controls = controls
        self._evidence = evidence
        self._quiescence = quiescence

    @contextmanager
    def hold(
        self, allocation: AllocationToken, writer: ResourceOwner, op: OperationContext
    ) -> Iterator[RecoverySession]:
        allocation = AllocationToken.model_validate(allocation)
        writer = ResourceOwner.model_validate(writer)
        op = OperationContext.model_validate(op)
        if (
            op.mode != "cleanup"
            or op.run_id != allocation.owner.run_id
            or op.owner_id != allocation.owner.owner_id
            or op.attempt_id != allocation.attempt_id
            or op.allocation_id != allocation.allocation_id
            or op.recovery_ref != allocation.recovery_ref
            or writer.run_id != allocation.owner.run_id
            or writer == allocation.owner
        ):
            raise OwnershipConflict(
                "Recovery session needs exact cleanup scope and distinct writer"
            )
        guard = self._controls.bind(op)
        guard.checkpoint()
        name = (
            hashlib.sha256(
                json.dumps(
                    [allocation.provider_id, allocation.expected_resource_id]
                ).encode()
            ).hexdigest()
            + ".recovery.json"
        )
        directory = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        lock: int | None = None
        session: _FileRecoverySession | None = None
        primary: BaseException | None = None
        try:
            try:
                lock = os.open(
                    name + ".lock",
                    os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                    0o600,
                    dir_fd=directory,
                )
            except OSError as error:
                raise EvidenceIntegrityError("Unsafe recovery lock") from error
            if not stat.S_ISREG(os.fstat(lock).st_mode):
                raise EvidenceIntegrityError("Recovery lock must be a regular file")
            while True:
                guard.checkpoint()
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    guard.wait(0.02)
            session = _FileRecoverySession(
                self, directory, lock, name, allocation, writer, op, guard
            )
            session.checkpoint()
            yield session
        except BaseException as error:
            primary = error
            raise
        finally:
            if session is not None:
                session.active = False
            errors: list[Exception] = []
            for fd in (lock, directory):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError as error:
                        errors.append(error)
            if errors:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Recovery session and close failed", [primary, *errors]
                    ) from None
                raise ExceptionGroup("Recovery session close failed", errors)


class _FileRecoverySession:
    """Only usable inside hold(); do not transfer this handle to a worker."""

    def __init__(
        self,
        store: FileRecoverySessions,
        directory: int,
        lock: int,
        name: str,
        allocation: AllocationToken,
        writer: ResourceOwner,
        op: OperationContext,
        guard: OperationControl,
    ) -> None:
        self.store, self.directory, self.lock, self.name = store, directory, lock, name
        self.allocation, self.writer, self.op, self.guard = (
            allocation,
            writer,
            op,
            guard,
        )
        self.process, self.thread = os.getpid(), threading.get_ident()
        self.active = True
        self.started: RecoveryIntent | None = None

    def checkpoint(self) -> None:
        if (
            not self.active
            or os.getpid() != self.process
            or threading.get_ident() != self.thread
        ):
            raise OwnershipConflict(
                "Recovery session is expired or belongs to another execution context"
            )
        self.guard.checkpoint()
        opened = os.fstat(self.lock)
        try:
            current = os.stat(
                self.name + ".lock", dir_fd=self.directory, follow_symlinks=False
            )
        except OSError as error:
            raise OwnershipConflict("Stable recovery lock is unavailable") from error
        if not stat.S_ISREG(current.st_mode) or (opened.st_dev, opened.st_ino) != (
            current.st_dev,
            current.st_ino,
        ):
            raise OwnershipConflict("Stable recovery lock was replaced")

    def _load(self) -> RecoverySessionRecord | None:
        self.checkpoint()
        try:
            fd = os.open(
                self.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=self.directory,
            )
        except FileNotFoundError:
            return None
        except OSError as error:
            raise EvidenceIntegrityError("Unsafe recovery snapshot") from error
        primary: BaseException | None = None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise EvidenceIntegrityError("Recovery snapshot must be a regular file")
            chunks: list[bytes] = []
            remaining = self.store._MAX_BYTES + 1
            while remaining:
                chunk = os.read(fd, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                os.close(fd)
            except OSError as error:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Recovery read and close failed", [primary, error]
                    ) from None
                raise
        if len(raw) > self.store._MAX_BYTES:
            raise EvidenceIntegrityError("Recovery snapshot exceeds limit")
        try:
            record = RecoverySessionRecord.model_validate_json(raw)
        except ValidationError as error:
            raise EvidenceIntegrityError("Invalid recovery lineage") from error
        if record.allocation != self.allocation:
            raise OwnershipConflict("Recovery snapshot belongs to another allocation")
        self.checkpoint()
        return record

    def _write(self, record: RecoverySessionRecord) -> None:
        self.checkpoint()
        raw = record.model_dump_json().encode()
        reserve = (
            self.store._RECEIPT_RESERVE
            if record.attempts[-1].receipt_ref is None
            else 0
        )
        if len(raw) + reserve > self.store._MAX_BYTES:
            raise EvidenceIntegrityError(
                "Recovery history must retain receipt commit space"
            )
        name = ".pending-recovery-" + uuid.uuid4().hex
        fd: int | None = None
        created = False
        primary: BaseException | None = None
        try:
            fd = os.open(
                name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=self.directory
            )
            created = True
            view = memoryview(raw)
            offset = 0
            while offset < len(view):
                written = os.write(fd, view[offset:])
                if written <= 0:
                    raise OSError("Recovery snapshot write made no progress")
                offset += written
            os.fsync(fd)
            self.checkpoint()
            os.replace(
                name, self.name, src_dir_fd=self.directory, dst_dir_fd=self.directory
            )
            created = False
            os.fsync(self.directory)
            self.checkpoint()
        except BaseException as error:
            primary = error
            raise
        finally:
            errors: list[Exception] = []
            if created:
                try:
                    os.unlink(name, dir_fd=self.directory)
                except FileNotFoundError:
                    pass
                except OSError as error:
                    errors.append(error)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError as error:
                    errors.append(error)
            if errors:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Recovery snapshot and cleanup failed", [primary, *errors]
                    ) from None
                raise ExceptionGroup("Recovery snapshot cleanup failed", errors)

    def read(self) -> RecoveryReceipt | None:
        record = self._load()
        if record is None:
            return None
        ref = record.attempts[-1].receipt_ref
        if ref is None:
            return None
        try:
            receipt = RecoveryReceipt.model_validate_json(
                self.store._evidence.read(ref, control=self.guard)
            )
        except ValidationError as error:
            raise EvidenceIntegrityError("Invalid stored recovery receipt") from error
        if receipt.intent != record.attempts[-1].intent:
            raise OwnershipConflict(
                "Stored receipt differs from the committed recovery intent"
            )
        self.checkpoint()
        return receipt

    def begin(self, intent: RecoveryIntent) -> None:
        intent = RecoveryIntent.model_validate(intent)
        if (
            intent.allocation != self.allocation
            or intent.recovery_writer != self.writer
            or intent.operation_id != self.op.operation_id
        ):
            raise OwnershipConflict(
                "Intent must bind this session's exact writer and operation"
            )
        record = self._load()
        if record is not None and record.attempts[-1].receipt_ref is not None:
            raise OwnershipConflict("Completed recovery cannot be started again")
        if self.started is not None:
            if intent != self.started:
                raise OwnershipConflict(
                    "One held session cannot start multiple intents"
                )
            if record is not None and record.attempts[-1].intent == intent:
                return
        predecessor = None
        if record is not None:
            prior = record.attempts[-1].intent.recovery_writer
            predecessor = WriterTerminationReceipt.model_validate(
                self.store._quiescence.confirm_ended(prior, self.op)
            )
            if predecessor.owner != prior:
                raise OwnershipConflict(
                    "Termination authority returned another recovery writer"
                )
            for ref in predecessor.evidence:
                self.store._evidence.read(ref, control=self.guard)
                self.checkpoint()
        attempt = RecoverySessionAttempt(
            intent=intent, predecessor_termination=predecessor
        )
        updated = RecoverySessionRecord(
            allocation=self.allocation,
            attempts=(*record.attempts, attempt) if record else (attempt,),
        )
        self.started = intent
        self._write(updated)

    def commit(self, receipt: RecoveryReceipt) -> None:
        receipt = RecoveryReceipt.model_validate(receipt)
        record = self._load()
        if record is None or receipt.intent != record.attempts[-1].intent:
            raise OwnershipConflict("Receipt must close the exact persisted intent")
        if record.attempts[-1].receipt_ref is not None:
            if self.read() != receipt:
                raise OwnershipConflict("Committed recovery receipt cannot be replaced")
            return
        if self.started != receipt.intent:
            raise OwnershipConflict("Only this held session's begun intent may commit")
        ref = self.store._evidence.put(
            receipt.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="recovery-receipt/1",
                visibility="private",
                producer=receipt.intent.binding.component_id,
            ),
            control=self.guard,
        )
        self.checkpoint()
        last = record.attempts[-1]
        finished = RecoverySessionAttempt(
            intent=last.intent,
            predecessor_termination=last.predecessor_termination,
            receipt_ref=ref,
        )
        self._write(
            RecoverySessionRecord(
                allocation=self.allocation, attempts=(*record.attempts[:-1], finished)
            )
        )
