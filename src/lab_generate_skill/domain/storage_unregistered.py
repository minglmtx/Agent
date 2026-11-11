"""Factual absence in original unchanged history, never an I/O retry permit."""

import hashlib
from typing import Literal
from pydantic import Field
from .validation import Contract, Sha256, Identifier
from .evidence_sessions import EvidenceSessionBinding, EvidenceWorkerInstance
from .evidence_session_state import EvidenceSessionSnapshot
from .lifecycle import OperationContext
from .storage_termination import StorageProcessEnd


class StorageUnregisteredExchange(Contract):
    schema_version: Literal["storage-unregistered-exchange/1"] = (
        "storage-unregistered-exchange/1"
    )
    exchange_id: Identifier
    request_sha256: Sha256
    binding: EvidenceSessionBinding
    operation: OperationContext
    ending: StorageProcessEnd
    observer: EvidenceWorkerInstance
    revision: int = Field(ge=0)
    snapshot_sha256: Sha256

    def check(
        self,
        snapshot: EvidenceSessionSnapshot,
        *,
        exchange_id: str,
        request_sha256: str,
        binding: EvidenceSessionBinding,
        operation: OperationContext,
        ending: StorageProcessEnd | None,
        observer: EvidenceWorkerInstance,
        expected_revision: int,
    ) -> None:
        if (
            (
                self.exchange_id,
                self.request_sha256,
                self.binding,
                self.operation,
                self.ending,
                self.observer,
                self.revision,
            )
            != (
                exchange_id,
                request_sha256,
                binding,
                operation,
                ending,
                observer,
                expected_revision,
            )
            or snapshot.binding != binding
            or snapshot.revision != expected_revision
            or hashlib.sha256(snapshot.model_dump_json().encode()).hexdigest()
            != self.snapshot_sha256
            or self.ending.request_sha256 != request_sha256
            or (self.ending.controller.node_id, self.ending.controller.boot_id)
            != (observer.node_id, observer.boot_id)
            or observer.process_id
            in (self.ending.controller.process_id, self.ending.process_id)
            or operation.mode != "cleanup"
            or operation.cancellation_ref is not None
            or operation.parent_operation_id is None
            or any(e.intent.exchange_id == exchange_id for e in snapshot.entries)
            or (snapshot.entries and not snapshot.entries[-1].reusable)
        ):
            raise ValueError(
                "Unregistered exchange differs from original ended request/history"
            )
