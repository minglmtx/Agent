"""Worker-local single current pointer using stable lock and atomic snapshot.

No asset copying, candidate repair or default authority. An independent birth
record prevents empty reconstruction when snapshot/marker disappear. After a
write attempt any error retains its type/chain plus release_current_candidate;
read with a fresh bounded operation to reconcile, never infer non-commit.
"""

from pathlib import Path
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.release_activation import (
    ReleaseDeployment,
    ReleaseSwitch,
    check_publication_operation,
)
from lab_generate_skill.domain.release_current import (
    ReleaseCurrentSnapshot,
    MAX_CURRENT_BYTES,
    switch_release,
)
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.release_current import ReleaseCurrentAuthority
from lab_generate_skill.adapters.storage.atomic_snapshot import (
    AtomicSnapshotFile,
    SnapshotTransaction,
)
from lab_generate_skill.adapters.processes.wire_json import json_object


class FileReleaseCurrent:
    def __init__(
        self,
        root: Path,
        deployment: ReleaseDeployment,
        controls: OperationControls,
        authority: ReleaseCurrentAuthority,
    ) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("Current root must be a trusted absolute directory")
        self._root = root
        self._deployment = ReleaseDeployment.model_validate(deployment)
        self._controls, self._authority = controls, authority
        self._file = AtomicSnapshotFile(
            root, "system-current.json", max_bytes=MAX_CURRENT_BYTES
        )

    def _access(self, op: OperationContext) -> OperationControl:
        control = self._controls.bind(op)
        control.checkpoint()
        self._authority.authorize_access(self._deployment, op, control)
        control.checkpoint()
        if self._root.resolve(strict=True) != self._root or not self._root.is_dir():
            raise EvidenceIntegrityError("Current root must be canonical")
        return control

    @staticmethod
    def _birth(snapshot: ReleaseCurrentSnapshot) -> bytes:
        return (
            ReleaseCurrentSnapshot(
                deployment=snapshot.deployment, initialized_by=snapshot.initialized_by
            )
            .model_dump_json()
            .encode()
        )

    def _read(self, transaction: SnapshotTransaction) -> ReleaseCurrentSnapshot:
        raw = transaction.read()
        if raw is None:
            raise EvidenceNotFound("Current deployment has not been initialized")
        try:
            json_object(raw)
            snapshot = ReleaseCurrentSnapshot.model_validate_json(raw)
        except ValueError as error:
            raise EvidenceIntegrityError("Invalid release current snapshot") from error
        if snapshot.deployment != self._deployment:
            raise OwnershipConflict("Current deployment or capacity changed")
        if transaction.pending("0" * 64) != self._birth(snapshot):
            raise EvidenceIntegrityError("Current birth record missing or changed")
        return snapshot

    def initialize(self, operation: OperationContext) -> ReleaseCurrentSnapshot:
        op = OperationContext.model_validate(operation)
        check_publication_operation(op)
        candidate = ReleaseCurrentSnapshot(
            deployment=self._deployment, initialized_by=op
        )
        birth = self._birth(candidate)
        if len(birth) > 8192:
            raise ValueError("Publication initialization exceeds birth record budget")
        control = self._access(op)
        committing = False
        try:
            with self._file.locked(control) as transaction:
                if transaction.read() is not None:
                    candidate = self._read(transaction)
                    committing = True
                    transaction.confirm()
                else:
                    if transaction.pending("0" * 64) is not None:
                        raise EvidenceIntegrityError(
                            "Used current cannot be initialized again"
                        )
                    committing = True
                    transaction.retain_pending("0" * 64, birth)
                    transaction.write(candidate.model_dump_json().encode())
            control.checkpoint()
            return candidate
        except BaseException as error:
            if committing:
                error.release_current_candidate = candidate  # type: ignore[attr-defined]
            raise

    def read(self, operation: OperationContext) -> ReleaseCurrentSnapshot:
        op = OperationContext.model_validate(operation)
        control = self._access(op)
        with self._file.locked(control, create_lock=False) as transaction:
            result = self._read(transaction)
            transaction.checkpoint()
        control.checkpoint()
        return result

    def activate(self, change: ReleaseSwitch) -> ReleaseCurrentSnapshot:
        change = ReleaseSwitch.model_validate(change)
        control = self._access(change.operation)
        candidate: ReleaseCurrentSnapshot | None = None
        committing = False
        try:
            with self._file.locked(control, create_lock=False) as transaction:
                prior = self._read(transaction)
                candidate = switch_release(prior, change)
                if candidate != prior:
                    self._authority.authorize_switch(prior, change, control)
                    transaction.checkpoint()
                    committing = True
                    transaction.write(candidate.model_dump_json().encode())
                else:
                    committing = True
                    transaction.confirm()
                transaction.checkpoint()
            control.checkpoint()
            return candidate
        except BaseException as error:
            if committing:
                error.release_current_candidate = candidate  # type: ignore[attr-defined]
            raise
