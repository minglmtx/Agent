"""Read-only original recovery integrity, separate from four page predicates.

This confirms held recovery material, not current database equality, writer
closure, restoration, safe Reset or business success. Its parent must authorize
the original closed-browser guard phase before sending this fixed collector.
"""

from typing import Literal, Self
import hashlib
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from ..database_contract import DatabaseReply
from ..artifact_contract import AdminArtifactSnapshot
from ..search_contract import AdminSearchSnapshot
from .navigation_recovery_contract import NavigationRecoverySnapshot


class NavigationSnapshotIntegrity(Contract):
    schema_version: Literal["admin-navigation-snapshot-integrity/1"] = (
        "admin-navigation-snapshot-integrity/1"
    )
    task: TaskIdentity
    operation: OperationContext
    snapshot_ref: EvidenceRef
    state_snapshot_sha256: Sha256
    database: DatabaseReply
    artifacts: AdminArtifactSnapshot
    search: AdminSearchSnapshot

    @model_validator(mode="after")
    def readonly(self) -> Self:
        private_state_ref(self.snapshot_ref, "admin-navigation-recovery/1")
        if self.operation.mode != "execute" or self.database.operation != "verify":
            raise ValueError("Original read-only verification is required")
        return self

    def require_original(self, saved: NavigationRecoverySnapshot) -> None:
        state, request = saved.state, saved.request
        raw = saved.model_dump_json().encode()
        if (self.snapshot_ref.sha256, self.snapshot_ref.size_bytes) != (
            hashlib.sha256(raw).hexdigest(),
            len(raw),
        ):
            raise ValueError(
                "Navigation verification changed the original snapshot reference"
            )
        if (
            self.task,
            self.state_snapshot_sha256,
            self.database.sha256,
            self.database.size_bytes,
            self.artifacts,
            self.search,
        ) != (
            request.task,
            state.digest,
            state.database.sha256,
            state.database.size_bytes,
            state.artifacts,
            state.search,
        ) or any(
            getattr(self.operation, name) != getattr(request.operation, name)
            for name in (
                "run_id",
                "owner_id",
                "attempt_id",
                "allocation_id",
                "recovery_ref",
            )
        ):
            raise ValueError(
                "Navigation verification changed original recovery material"
            )
