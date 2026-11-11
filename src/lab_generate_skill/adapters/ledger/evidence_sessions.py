"""Worker-local session persistence, not a parent-process evidence port.

Caller must supervise this entire adapter, including authority and lock I/O.
Constructor is I/O-free; trusted bootstrap supplies one physical root, storage
identity/config and mandatory authority. No default admission or root creation.
Read/update require the original lock; only explicit create may establish it.
AtomicSnapshotFile owns writes, durability, stable locking and cleanup errors.
"""

from collections.abc import Callable
from pathlib import Path
from pydantic import TypeAdapter
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
)
from lab_generate_skill.domain.validation import Identifier, Sha256
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceSessionCapacity,
    EvidenceOperationIntent,
    EvidenceOperationOutcome,
    EvidenceSessionResolution,
    check_evidence_cleanup,
)
from lab_generate_skill.domain.evidence_session_state import (
    EvidenceSessionSnapshot,
    begin_evidence_exchange,
    record_evidence_outcome,
    resolve_evidence_exchange,
)
from lab_generate_skill.domain.evidence_session_commit import (
    EvidenceSessionCommitUnconfirmed,
)
from lab_generate_skill.ports.evidence_sessions import EvidenceSessionAuthority
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.adapters.storage.atomic_snapshot import (
    AtomicSnapshotFile,
    SnapshotTransaction,
)
from lab_generate_skill.adapters.processes.wire_json import json_object


class FileEvidenceSessions:
    def __init__(
        self,
        root: Path,
        storage_id: str,
        storage_config_sha256: str,
        controls: OperationControls,
        authority: EvidenceSessionAuthority,
    ) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("Session root must be a trusted absolute path")
        self._root = root
        self._storage = TypeAdapter(Identifier).validate_python(storage_id, strict=True)
        self._config = TypeAdapter(Sha256).validate_python(
            storage_config_sha256, strict=True
        )
        self._controls, self._authority = controls, authority

    def _check(
        self, binding: EvidenceSessionBinding, op: OperationContext
    ) -> tuple[EvidenceSessionBinding, OperationContext, AtomicSnapshotFile]:
        binding = EvidenceSessionBinding.model_validate(binding)
        op = OperationContext.model_validate(op)
        if (binding.storage_id, binding.storage_config_sha256) != (
            self._storage,
            self._config,
        ):
            raise OwnershipConflict(
                "Session differs from trusted storage configuration"
            )
        if (op.run_id, op.owner_id) != (binding.owner.run_id, binding.owner.owner_id):
            raise OwnershipConflict("Session operation belongs to another owner")
        control = self._controls.bind(op)
        control.checkpoint()
        self._authority.authorize_binding(binding, op)
        control.checkpoint()
        return (
            binding,
            op,
            AtomicSnapshotFile(
                self._root,
                binding.namespace_key + ".evidence-session.json",
                max_bytes=8 * 1024 * 1024,
            ),
        )

    @staticmethod
    def _fence(snapshot: EvidenceSessionSnapshot) -> bytes:
        # Independent immutable birth record prevents empty reconstruction when
        # both the snapshot and its initialization marker disappear.
        return (
            EvidenceSessionSnapshot(
                binding=snapshot.binding, capacity=snapshot.capacity
            )
            .model_dump_json()
            .encode()
        )

    def _read(
        self, transaction: SnapshotTransaction, binding: EvidenceSessionBinding
    ) -> EvidenceSessionSnapshot:
        snapshot = self._decode(transaction.read(), binding)
        if transaction.pending("0" * 64) != self._fence(snapshot):
            raise EvidenceIntegrityError(
                "Original session birth record missing or changed"
            )
        return snapshot

    @staticmethod
    def _decode(
        raw: bytes | None, binding: EvidenceSessionBinding
    ) -> EvidenceSessionSnapshot:
        if raw is None:
            raise EvidenceNotFound("No original evidence session snapshot")
        try:
            json_object(
                raw
            )  # Reject duplicate fields/nonfinite JSON before model parsing.
            snapshot = EvidenceSessionSnapshot.model_validate_json(raw)
        except ValueError as error:
            raise EvidenceIntegrityError("Invalid original evidence session") from error
        if snapshot.binding != binding:
            raise OwnershipConflict("Evidence session binding cannot be changed")
        return snapshot

    def create(
        self,
        binding: EvidenceSessionBinding,
        capacity: EvidenceSessionCapacity,
        op: OperationContext,
    ) -> EvidenceSessionSnapshot:
        capacity = EvidenceSessionCapacity.model_validate(capacity)
        binding, op = EvidenceSessionBinding.model_validate(
            binding
        ), OperationContext.model_validate(op)
        if op.mode != "execute":
            raise OwnershipConflict("Cleanup cannot create an evidence session")
        candidate = EvidenceSessionSnapshot(binding=binding, capacity=capacity)
        binding, op, file = self._check(binding, op)
        committing = False
        try:
            with file.locked(self._controls.bind(op)) as transaction:
                raw = transaction.read()
                if raw is not None:
                    prior = self._read(transaction, binding)
                    if prior.capacity != capacity:
                        raise OwnershipConflict("Session capacity is immutable")
                    return prior
                if transaction.pending("0" * 64) is not None:
                    raise EvidenceIntegrityError(
                        "Used session cannot be initialized again"
                    )
                committing = True
                transaction.retain_pending("0" * 64, self._fence(candidate))
                transaction.write(candidate.model_dump_json().encode())
            return candidate
        except BaseException as error:
            if committing:
                if isinstance(error, Exception):
                    raise EvidenceSessionCommitUnconfirmed(candidate) from error
                setattr(error, "evidence_session_candidate", candidate)
            raise

    def read(
        self, binding: EvidenceSessionBinding, op: OperationContext
    ) -> EvidenceSessionSnapshot:
        binding, op, file = self._check(binding, op)
        with file.locked(self._controls.bind(op), create_lock=False) as transaction:
            snapshot = self._read(transaction, binding)
            transaction.checkpoint()
        return snapshot

    def _change(
        self,
        binding: EvidenceSessionBinding,
        op: OperationContext,
        change: Callable[[EvidenceSessionSnapshot], EvidenceSessionSnapshot],
    ) -> EvidenceSessionSnapshot:
        binding, op, file = self._check(binding, op)
        candidate: EvidenceSessionSnapshot | None = None
        committing = False
        try:
            with file.locked(self._controls.bind(op), create_lock=False) as transaction:
                prior = self._read(transaction, binding)
                candidate = change(prior)
                transaction.checkpoint()
                if candidate != prior:
                    committing = True
                    transaction.write(candidate.model_dump_json().encode())
            return candidate
        except BaseException as error:
            if committing and candidate is not None:
                if isinstance(error, Exception):
                    raise EvidenceSessionCommitUnconfirmed(candidate) from error
                setattr(error, "evidence_session_candidate", candidate)
            raise

    def begin(
        self,
        binding: EvidenceSessionBinding,
        intent: EvidenceOperationIntent,
        expected_revision: int,
    ) -> EvidenceSessionSnapshot:
        intent = EvidenceOperationIntent.model_validate(intent)

        def change(prior: EvidenceSessionSnapshot) -> EvidenceSessionSnapshot:
            candidate = begin_evidence_exchange(prior, intent, expected_revision)
            self._authority.authorize_intent(prior.binding, intent)
            return candidate

        return self._change(binding, intent.operation, change)

    def record_outcome(
        self,
        binding: EvidenceSessionBinding,
        outcome: EvidenceOperationOutcome,
        expected_revision: int,
        op: OperationContext,
    ) -> EvidenceSessionSnapshot:
        outcome, op = EvidenceOperationOutcome.model_validate(
            outcome
        ), OperationContext.model_validate(op)
        if op != outcome.operation:
            check_evidence_cleanup(outcome.operation, op)

        def change(prior: EvidenceSessionSnapshot) -> EvidenceSessionSnapshot:
            candidate = record_evidence_outcome(prior, outcome, expected_revision)
            if candidate != prior:
                original = next(
                    e.intent
                    for e in prior.entries
                    if e.intent.exchange_id == outcome.exchange_id
                )
                self._authority.verify_outcome(prior.binding, original, outcome, op)
            return candidate

        return self._change(binding, op, change)

    def resolve(
        self,
        binding: EvidenceSessionBinding,
        resolution: EvidenceSessionResolution,
        expected_revision: int,
    ) -> EvidenceSessionSnapshot:
        resolution = EvidenceSessionResolution.model_validate(resolution)

        def change(prior: EvidenceSessionSnapshot) -> EvidenceSessionSnapshot:
            candidate = resolve_evidence_exchange(prior, resolution, expected_revision)
            if candidate != prior:
                original = next(
                    e.intent
                    for e in prior.entries
                    if e.intent.exchange_id == resolution.exchange_id
                )
                self._authority.verify_resolution(prior.binding, original, resolution)
            return candidate

        return self._change(binding, resolution.operation, change)
