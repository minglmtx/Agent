"""Controlled EvidenceStore backed by fixed registered worker and resolver.

initialize is explicit and never a read/put fallback. One local invocation at a
time; concurrent callers fail immediately while durable CAS handles other store
instances. Only confirmed resolution restores readiness. A quarantined instance
cannot reinitialize or retry; retain last_exchange and original durable history.
All filesystem/ledger effects are in fixed children. This is not a hard bound on
blocking admission/control/Popen, or production run/release authorization.
"""

import math
from contextlib import contextmanager
from collections.abc import Iterator
from lab_generate_skill.domain.evidence_read_scope import EvidenceReadScope
from threading import Lock
from typing import Literal
from uuid import uuid4
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.ports.evidence_operations import EvidenceOperationFactory
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControl,
    OperationControls,
)
from .registered_protocol import RegisteredStorageCommand
from .registered_transport import RegisteredStorageTransport
from .resolver_transport import StorageResolverTransport
from lab_generate_skill.domain.evidence_io import EvidenceCommand
from .worker_protocol import decode_reply
from .managed_exchange import execute_managed_exchange
from .managed_result import ManagedEvidenceResult


class ManagedEvidenceStore:
    def __init__(
        self,
        binding: EvidenceSessionBinding,
        config: EvidenceStorageConfig,
        controller: ProcessIdentity,
        operations: EvidenceOperationFactory,
        transport: RegisteredStorageTransport,
        resolver: StorageResolverTransport,
        clock: Clock,
        cleanup_controls: OperationControls,
        *,
        cleanup_seconds: float,
    ) -> None:
        self._binding = EvidenceSessionBinding.model_validate(binding)
        self._config = EvidenceStorageConfig.model_validate(config)
        self._controller = ProcessIdentity.model_validate(controller)
        if (binding.storage_id, binding.storage_config_sha256) != (
            config.storage_id,
            config.sha256,
        ) or operations.binding != binding:
            raise OwnershipConflict("Storage assembly differs from original binding")
        if type(cleanup_seconds) not in (int, float):
            raise TypeError("Cleanup duration must be an exact number")
        try:
            if not math.isfinite(cleanup_seconds) or not 0 < cleanup_seconds <= 86400:
                raise ValueError(
                    "Cleanup duration must be finite, positive and bounded"
                )
        except OverflowError as error:
            raise ValueError("Cleanup duration outside range") from error
        self._operations, self._transport, self._resolver = (
            operations,
            transport,
            resolver,
        )
        self._clock, self._cleanup_controls = clock, cleanup_controls
        self._cleanup_seconds = float(cleanup_seconds)
        self._lock = Lock()
        self._state: Literal["new", "ready", "quarantined"] = "new"
        self._snapshot: EvidenceSessionSnapshot | None = None
        self._last: ManagedEvidenceResult | None = None

    @property
    def state(self) -> Literal["new", "ready", "quarantined"]:
        return self._state

    @property
    def last_exchange(self) -> ManagedEvidenceResult | None:
        return self._last

    def _enter(self, expected: str) -> None:
        if not self._lock.acquire(blocking=False):
            raise InvalidTransition("Storage invocation already in progress")
        if self._state != expected:
            self._lock.release()
            raise InvalidTransition("Storage instance is not " + expected)

    def initialize(self, control: OperationControl) -> EvidenceSessionSnapshot:
        """Explicitly create/read original history; never discard uncertain state."""
        return self._initialize(control, existing_only=False)

    def open_existing(self, control: OperationControl) -> EvidenceSessionSnapshot:
        """Read an existing ready namespace; never create/reconstruct its history."""
        return self._initialize(control, existing_only=True)

    def _initialize(
        self, control: OperationControl, *, existing_only: bool
    ) -> EvidenceSessionSnapshot:
        self._enter("new")
        try:
            prepared = self._operations.prepare(
                ("open-existing-" if existing_only else "initialize-") + uuid4().hex,
                control,
            )
            command = RegisteredStorageCommand(
                schema_version=(
                    "registered-storage-command/4"
                    if existing_only
                    else "registered-storage-command/3"
                ),
                action="open_existing" if existing_only else "create",
                binding=self._binding,
                config=self._config,
                operation=prepared.operation,
                controller=self._controller,
            )
            self._state = "quarantined"
            done = self._transport.execute(command, b"", prepared.control)
            snapshot = done.result.snapshot
            if (
                snapshot is None
                or done.ending is None
                or (existing_only and not snapshot.entries)
                or (snapshot.entries and not snapshot.entries[-1].reusable)
            ):
                raise InvalidTransition("Original storage session is not ready")
            self._snapshot, self._state = snapshot, "ready"
            return snapshot
        finally:
            self._lock.release()

    @contextmanager
    def read_scope(
        self, control: OperationControl
    ) -> Iterator[tuple[EvidenceReadScope, OperationControl]]:
        """Hold the ready original store while a supervised readonly proof runs.

        No CAS/session transaction is created or skipped. The mandatory parent
        admission still verifies the actual scope for the fixed readonly child.
        """
        self._enter("ready")
        try:
            assert self._snapshot is not None
            prepared = self._operations.prepare("source-proof-" + uuid4().hex, control)
            scope = EvidenceReadScope(
                binding=self._binding,
                config=self._config,
                controller=self._controller,
                operation=prepared.operation,
                revision=self._snapshot.revision,
            )
            yield scope, prepared.control
            control.checkpoint()
        finally:
            self._lock.release()

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        if not isinstance(reference, EvidenceRef):
            raise TypeError("Evidence read requires EvidenceRef")
        reference = EvidenceRef.model_validate(reference)
        return self._perform("read", reference, None, b"", control)

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        if type(data) is not bytes:
            raise TypeError("Evidence payload must be immutable bytes")
        if len(data) > self._config.max_object_bytes:
            raise ValueError("Evidence payload exceeds frozen storage limit")
        reference = evidence_reference(data, metadata)
        self._perform("put", reference, metadata, data, control)
        return reference

    def _perform(
        self,
        kind: Literal["read", "put"],
        reference: EvidenceRef,
        metadata: EvidenceMetadata | None,
        payload: bytes,
        control: OperationControl,
    ) -> bytes:
        # Validate complete parameters before local state changes or transport.
        io = EvidenceCommand(
            exchange_id="evidence-" + uuid4().hex,
            operation=kind,
            root=self._config.evidence_root,
            max_object_bytes=self._config.max_object_bytes,
            reference=reference,
            metadata=metadata,
        )
        self._enter("ready")
        try:
            assert self._snapshot is not None
            prepared = self._operations.prepare(io.exchange_id, control)
            command = RegisteredStorageCommand(
                action="exchange",
                binding=self._binding,
                config=self._config,
                operation=prepared.operation,
                controller=self._controller,
                expected_revision=self._snapshot.revision,
                io=io,
            )
            self._state = "quarantined"
            result = execute_managed_exchange(
                command,
                payload,
                prepared.control,
                self._transport,
                self._resolver,
                self._clock,
                self._cleanup_controls,
                self._cleanup_seconds,
                expected_snapshot=self._snapshot,
            )
            self._last = result
            if result.reusable:
                self._snapshot, self._state = result.snapshot, "ready"
            elif not result.attempted:
                self._state = "ready"  # admission/validation failed before launch
            result.raise_errors()
            assert result.execution is not None
            reply, data = decode_reply(io, result.execution.result.raw_reply)
            if reply.error is not None:
                raise AssertionError("Confirmed execution contains a failed reply")
            control.checkpoint()
            return data
        finally:
            self._lock.release()
