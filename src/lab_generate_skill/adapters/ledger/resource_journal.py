"""ResourceJournal/2: durable intent, once-only acquisition and append-only facts.

Uses the shared AtomicSnapshotFile for stable locks, birth/initialization fences,
publication/confirmation and cleanup errors. No resource launch or authority is
implemented here. The entire adapter/evidence access needs outer supervision.
Old v1 records are rejected, never silently imported into a new empty history.
"""

import hashlib
import os
import re
from collections.abc import Callable
from pathlib import Path

from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    ResourceEvent,
    ResourceOwner,
    ResourceRecord,
    ResourceState,
    RecoveryPlan,
    require_resource_transition,
)
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.adapters.storage.atomic_snapshot import (
    AtomicSnapshotFile,
    SnapshotTransaction,
)
from lab_generate_skill.adapters.processes.wire_json import json_object


class FileResourceJournal:
    _MAX_BYTES = 1024 * 1024
    _BIRTH = "0" * 64

    def __init__(
        self,
        root: Path,
        owner: ResourceOwner,
        operations: OperationControls,
        evidence: EvidenceReader,
    ) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("Resource root must be a trusted absolute directory")
        self._root = root
        self._owner = ResourceOwner.model_validate(owner)
        self._operations, self._evidence = operations, evidence

    def _check(self, token: AllocationToken, op: OperationContext) -> None:
        if token.owner != self._owner or (
            op.owner_id,
            op.run_id,
            op.allocation_id,
            op.attempt_id,
            op.recovery_ref,
        ) != (
            self._owner.owner_id,
            self._owner.run_id,
            token.allocation_id,
            token.attempt_id,
            token.recovery_ref,
        ):
            raise OwnershipConflict(
                "Resource operation must retain exact owner/allocation"
            )

    @staticmethod
    def _filename(token: AllocationToken) -> str:
        return (
            hashlib.sha256(token.allocation_id.encode()).hexdigest() + ".resource.json"
        )

    def _file(self, token: AllocationToken) -> AtomicSnapshotFile:
        # An old namespace is not an empty new namespace. No implicit conversion.
        legacy = self._root / (
            hashlib.sha256(token.allocation_id.encode()).hexdigest() + ".json"
        )
        for prior in (legacy, legacy.with_name(legacy.name + ".lock")):
            try:
                prior.lstat()
            except FileNotFoundError:
                pass
            else:
                raise EvidenceIntegrityError(
                    "Legacy resource namespace requires explicit migration"
                )
        return AtomicSnapshotFile(
            self._root, self._filename(token), max_bytes=self._MAX_BYTES
        )

    @staticmethod
    def _decode(raw: bytes | None) -> ResourceRecord:
        if raw is None:
            raise EvidenceNotFound("Original resource registration is absent")
        try:
            json_object(raw)
            return ResourceRecord.model_validate_json(raw)
        except ValueError as error:
            raise EvidenceIntegrityError("Invalid original resource history") from error

    @staticmethod
    def _birth(record: ResourceRecord) -> bytes:
        return (
            ResourceRecord(token=record.token, events=record.events[:1])
            .model_dump_json()
            .encode()
        )

    def _read(
        self, tx: SnapshotTransaction, token: AllocationToken | None = None
    ) -> ResourceRecord:
        record = self._decode(tx.read())
        if token is not None and record.token != token:
            raise OwnershipConflict("Allocation ID already binds another token")
        if tx.file.name != self._filename(record.token):
            raise EvidenceIntegrityError("Resource filename and token disagree")
        if tx.pending(self._BIRTH) != self._birth(record):
            raise EvidenceIntegrityError(
                "Original resource birth record is missing or changed"
            )
        return record

    def _transaction(
        self,
        token: AllocationToken,
        op: OperationContext,
        update: Callable[[ResourceRecord | None], ResourceRecord],
        *,
        creating: bool = False,
    ) -> ResourceRecord:
        token, op = AllocationToken.model_validate(
            token
        ), OperationContext.model_validate(op)
        self._check(token, op)
        control = self._operations.bind(op)
        control.checkpoint()
        candidate: ResourceRecord | None = None
        committing = False
        try:
            with self._file(token).locked(control, create_lock=creating) as tx:
                raw = tx.read()
                if raw is None:
                    if not creating or tx.pending(self._BIRTH) is not None:
                        raise EvidenceIntegrityError(
                            "Used resource history cannot be recreated"
                        )
                    current = None
                else:
                    current = self._read(tx, token)
                candidate = update(current)
                tx.checkpoint()
                if candidate != current:
                    data = candidate.model_dump_json().encode()
                    if len(data) > self._MAX_BYTES:
                        raise EvidenceIntegrityError("Resource record exceeds limit")
                    committing = True
                    if current is None:
                        tx.retain_pending(self._BIRTH, self._birth(candidate))
                    tx.write(data)
                else:
                    # Readback alone is not durable acknowledgement of a prior
                    # lost fsync. Confirm original bytes without another event.
                    tx.confirm()
            return candidate
        except BaseException as error:
            if committing and candidate is not None:
                setattr(error, "resource_candidate", candidate)
            raise

    def register(self, token: AllocationToken, op: OperationContext) -> ResourceRecord:
        token, op = AllocationToken.model_validate(
            token
        ), OperationContext.model_validate(op)
        self._check(token, op)
        guard = self._operations.bind(op)
        guard.checkpoint()
        raw = self._evidence.read(token.recovery_ref, control=guard)
        json_object(raw)
        plan = RecoveryPlan.model_validate_json(raw)
        guard.checkpoint()
        if plan.owner != token.owner or plan.attempt_id != token.attempt_id:
            raise OwnershipConflict("Recovery plan must bind original owner/attempt")

        def update(current: ResourceRecord | None) -> ResourceRecord:
            if current is not None:
                for event in current.events:
                    if event.operation_id == op.operation_id and event.operation != op:
                        raise OwnershipConflict("Resource operation context changed")
                return current
            if op.mode != "execute":
                raise OwnershipConflict("Cleanup cannot register a new resource")
            return ResourceRecord(
                token=token, events=(ResourceEvent(operation=op, state="registered"),)
            )

        return self._transaction(token, op, update, creating=True)

    def read(self, token: AllocationToken, op: OperationContext) -> ResourceRecord:
        token, op = AllocationToken.model_validate(
            token
        ), OperationContext.model_validate(op)
        self._check(token, op)
        control = self._operations.bind(op)
        control.checkpoint()
        with self._file(token).locked(control, create_lock=False) as tx:
            record = self._read(tx, token)
        return record

    def records(
        self, owner: ResourceOwner, op: OperationContext
    ) -> tuple[ResourceRecord, ...]:
        owner, op = ResourceOwner.model_validate(
            owner
        ), OperationContext.model_validate(op)
        if owner != self._owner or (op.owner_id, op.run_id) != (
            owner.owner_id,
            owner.run_id,
        ):
            raise OwnershipConflict("Discovery requires original owner")
        control = self._operations.bind(op)
        control.checkpoint()
        directory = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        primary: BaseException | None = None
        try:
            names = os.listdir(directory)
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                os.close(directory)
            except BaseException as cleanup:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Resource discovery and close failed", [primary, cleanup]
                    ) from None
                raise
        snapshots: set[str] = set()
        for name in names:
            control.checkpoint()
            match = re.match(r"^([0-9a-f]{64}\.resource\.json)(?:$|\.)", name)
            if match:
                snapshots.add(match[1])
            elif name.endswith(".json") or re.fullmatch(
                r"[0-9a-f]{64}\.json\.lock", name
            ):
                raise EvidenceIntegrityError("Unrecognized or legacy resource history")
        result: list[ResourceRecord] = []
        for name in sorted(snapshots):
            file = AtomicSnapshotFile(self._root, name, max_bytes=self._MAX_BYTES)
            with file.locked(control, create_lock=False) as tx:
                record = self._read(tx)
                if record.token.owner == owner:
                    result.append(record)
        return tuple(result)

    def _advance(
        self,
        token: AllocationToken,
        state: ResourceState,
        evidence: tuple[EvidenceRef, ...],
        expected_revision: int,
        op: OperationContext,
        *,
        one_shot: bool = False,
    ) -> ResourceRecord:
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Expected revision must be a nonnegative integer")
        token, op = AllocationToken.model_validate(
            token
        ), OperationContext.model_validate(op)
        event = ResourceEvent(operation=op, state=state, evidence=evidence)
        if state in ("closing", "closed", "quarantined") and op.mode != "cleanup":
            raise OwnershipConflict("Cleanup state needs cleanup operation")
        if state in ("acquiring", "acquired") and op.mode != "execute":
            raise OwnershipConflict("Cleanup cannot acquire a resource")

        def update(current: ResourceRecord | None) -> ResourceRecord:
            if current is None:
                raise EvidenceNotFound("Register before resource effects")
            for previous in current.events:
                if previous.operation_id == op.operation_id:
                    if previous != event:
                        raise OwnershipConflict(
                            "Operation already binds another resource event"
                        )
                    if one_shot:
                        raise DispatchAlreadyCommitted(
                            "Resource acquisition already committed; never relaunch"
                        )
                    return current
            if current.revision != expected_revision:
                raise RevisionConflict(
                    "Resource revision changed; inspect original history"
                )
            require_resource_transition(current.state, state)
            return ResourceRecord(token=token, events=(*current.events, event))

        return self._transaction(token, op, update)

    def begin_acquire(
        self,
        token: AllocationToken,
        intent_ref: EvidenceRef,
        expected_revision: int,
        op: OperationContext,
    ) -> ResourceRecord:
        token, op = AllocationToken.model_validate(
            token
        ), OperationContext.model_validate(op)
        intent_ref = EvidenceRef.model_validate(intent_ref)
        self._check(token, op)
        if (
            op.mode != "execute"
            or intent_ref.visibility != "private"
            or intent_ref.content_schema != "resource-acquisition-intent/1"
        ):
            raise OwnershipConflict(
                "Acquisition requires private intent and execute context"
            )
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Expected revision must be a nonnegative integer")
        guard = self._operations.bind(op)
        guard.checkpoint()
        raw = self._evidence.read(intent_ref, control=guard)
        json_object(raw)
        intent = ResourceAcquisitionIntent.model_validate_json(raw)
        if intent.token != token or intent.operation != op:
            raise OwnershipConflict(
                "Stored acquisition intent differs from original command"
            )
        self._evidence.read(intent.configuration_ref, control=guard)
        guard.checkpoint()
        return self._advance(
            token, "acquiring", (intent_ref,), expected_revision, op, one_shot=True
        )

    def advance(
        self,
        token: AllocationToken,
        state: ResourceState,
        evidence: tuple[EvidenceRef, ...],
        expected_revision: int,
        op: OperationContext,
    ) -> ResourceRecord:
        if state == "acquiring":
            raise OwnershipConflict("Use once-only begin_acquire before effects")
        return self._advance(token, state, evidence, expected_revision, op)
