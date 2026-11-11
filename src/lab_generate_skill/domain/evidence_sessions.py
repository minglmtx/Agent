"""Evidence session ownership and facts; no I/O or recovery authorization.

Pending intent is durable before storage effects. A reply is not worker exit,
and exit is not storage health. Unknown calls may be reconciled, never replayed.
All termination/object/cleanup facts require a real authority at persistence.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal, Self
from pydantic import AwareDatetime, Field, field_validator, model_validator

from .evidence import EvidenceRef
from .evidence_io import EvidenceCommand
from .process_identity import ProcessIdentity
from .lifecycle import OperationContext, ResourceOwner
from .validation import Contract, Identifier, Sha256

MAX_INTENT_BYTES = 8192
MAX_OUTCOME_BYTES = 2048
MAX_RESOLUTION_BYTES = 8192


class EvidenceSessionBinding(Contract):
    schema_version: Literal["evidence-session-binding/2"] = "evidence-session-binding/2"
    storage_id: Identifier
    scope: Literal["run", "source"]
    source_task_id: Identifier | None
    session_id: Identifier
    owner: ResourceOwner
    release_id: Identifier
    storage_config_sha256: Sha256

    @model_validator(mode="after")
    def explicit_scope(self) -> Self:
        if (self.scope == "source") != (self.source_task_id is not None):
            raise ValueError("Only source storage scope requires a source task ID")
        return self

    @property
    def namespace_key(self) -> str:
        # Retain the original source key: old /1 records must fail validation at
        # the SAME filename, never be bypassed through a fresh empty namespace.
        key = (
            [self.storage_id, self.source_task_id]
            if self.scope == "source"
            else ["run", self.storage_id, self.owner.run_id]
        )
        raw = json.dumps(key, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()


class EvidenceSessionCapacity(Contract):
    schema_version: Literal["evidence-session-capacity/1"] = (
        "evidence-session-capacity/1"
    )
    max_exchanges: int = Field(ge=1, le=10000)
    max_resolutions_per_exchange: int = Field(ge=1, le=32)
    max_bytes: int = Field(ge=4096, le=8 * 1024 * 1024)


class EvidenceWorkerInstance(Contract):
    schema_version: Literal["evidence-worker-instance/1"] = "evidence-worker-instance/1"
    node_id: Identifier
    boot_id: Identifier
    process_id: int = Field(ge=1)
    start_ticks: int = Field(ge=1)


class EvidenceOperationIntent(Contract):
    schema_version: Literal["evidence-operation-intent/2"] = (
        "evidence-operation-intent/2"
    )
    exchange_id: Identifier
    operation: OperationContext
    worker: EvidenceWorkerInstance
    kind: Literal["read", "put"]
    reference: EvidenceRef
    command_sha256: Sha256
    command: EvidenceCommand
    controller: ProcessIdentity

    @model_validator(mode="after")
    def execution(self) -> Self:
        if (
            self.operation.mode != "execute"
            or self.operation.parent_operation_id is not None
        ):
            raise ValueError("New evidence intent requires original execute operation")
        if self.reference.uri != f"cas://sha256/{self.reference.sha256}":
            raise ValueError("Session intent must retain canonical CAS identity")
        if (
            self.command.exchange_id,
            self.command.operation,
            self.command.reference,
        ) != (self.exchange_id, self.kind, self.reference):
            raise ValueError("Durable descriptor differs from original intent")
        if (self.controller.node_id, self.controller.boot_id) != (
            self.worker.node_id,
            self.worker.boot_id,
        ) or self.controller.process_id == self.worker.process_id:
            raise ValueError(
                "Intent requires a distinct original controller on the worker node/boot"
            )
        if len(self.model_dump_json().encode()) > MAX_INTENT_BYTES:
            raise ValueError("Evidence intent exceeds byte budget")
        return self


class EvidenceOperationOutcome(Contract):
    schema_version: Literal["evidence-operation-outcome/1"] = (
        "evidence-operation-outcome/1"
    )
    outcome_id: Identifier
    exchange_id: Identifier
    operation: OperationContext
    reply_sha256: Sha256
    status: Literal["succeeded", "failed"]
    reason_code: Identifier | None = None

    @model_validator(mode="after")
    def result(self) -> Self:
        if (self.status == "failed") != (self.reason_code is not None):
            raise ValueError("Only failed evidence outcome has an error reason")
        if len(self.model_dump_json().encode()) > MAX_OUTCOME_BYTES:
            raise ValueError("Evidence outcome exceeds byte budget")
        return self


class EvidenceWorkerEnded(Contract):
    schema_version: Literal["evidence-worker-ended/1"] = "evidence-worker-ended/1"
    worker: EvidenceWorkerInstance
    observed_at: AwareDatetime
    returncode: int
    verifier_id: Identifier
    proof_sha256: Sha256

    @field_validator("observed_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class EvidenceSessionResolution(Contract):
    schema_version: Literal["evidence-session-resolution/1"] = (
        "evidence-session-resolution/1"
    )
    resolution_id: Identifier
    exchange_id: Identifier
    operation: OperationContext
    worker_end: EvidenceWorkerEnded | None
    object_state: Literal["present", "absent", "unknown"]
    cleanup_state: Literal["clean", "failed", "unknown"]
    reason_code: Identifier

    @model_validator(mode="after")
    def cleanup(self) -> Self:
        if self.operation.mode != "cleanup":
            raise ValueError(
                "Evidence resolution requires independent cleanup operation"
            )
        if len(self.model_dump_json().encode()) > MAX_RESOLUTION_BYTES:
            raise ValueError("Evidence resolution exceeds byte budget")
        return self


def check_evidence_cleanup(
    original: OperationContext, cleanup: OperationContext
) -> None:
    if (
        cleanup.mode != "cleanup"
        or cleanup.parent_operation_id != original.operation_id
        or (
            cleanup.run_id,
            cleanup.owner_id,
            cleanup.attempt_id,
            cleanup.allocation_id,
            cleanup.recovery_ref,
        )
        != (
            original.run_id,
            original.owner_id,
            original.attempt_id,
            original.allocation_id,
            original.recovery_ref,
        )
    ):
        raise ValueError(
            "Cleanup must preserve exact original evidence operation scope"
        )


def resolution_allows_reuse(
    outcome: EvidenceOperationOutcome | None, result: EvidenceSessionResolution
) -> bool:
    return (
        result.worker_end is not None
        and result.object_state != "unknown"
        and result.cleanup_state == "clean"
        and not (
            outcome is not None
            and outcome.status == "succeeded"
            and result.object_state != "present"
        )
    )


class EvidenceSessionEntry(Contract):
    schema_version: Literal["evidence-session-entry/1"] = "evidence-session-entry/1"
    intent: EvidenceOperationIntent
    outcome: EvidenceOperationOutcome | None = None
    resolutions: tuple[EvidenceSessionResolution, ...] = ()

    @property
    def reusable(self) -> bool:
        if not self.resolutions:
            return False
        return resolution_allows_reuse(self.outcome, self.resolutions[-1])

    @property
    def stage(self) -> Literal["pending", "returned", "quarantined", "resolved"]:
        if self.resolutions:
            return "resolved" if self.reusable else "quarantined"
        return "pending" if self.outcome is None else "returned"

    @model_validator(mode="after")
    def lineage(self) -> Self:
        intent = self.intent
        if self.outcome is not None and (
            self.outcome.exchange_id != intent.exchange_id
            or self.outcome.operation != intent.operation
        ):
            raise ValueError("Outcome must retain the original exchange and operation")
        ids: set[str] = set()
        operations: set[str] = set()
        for index, result in enumerate(self.resolutions):
            if result.exchange_id != intent.exchange_id:
                raise ValueError("Resolution belongs to another exchange")
            check_evidence_cleanup(intent.operation, result.operation)
            if (
                result.worker_end is not None
                and result.worker_end.worker != intent.worker
            ):
                raise ValueError(
                    "Termination must identify the exact worker incarnation"
                )
            if (
                result.resolution_id in ids
                or result.operation.operation_id in operations
            ):
                raise ValueError("Resolution identities cannot be duplicated")
            ids.add(result.resolution_id)
            operations.add(result.operation.operation_id)
            reusable = resolution_allows_reuse(self.outcome, result)
            if reusable and index != len(self.resolutions) - 1:
                raise ValueError("Resolved evidence exchange is immutable")
        return self
